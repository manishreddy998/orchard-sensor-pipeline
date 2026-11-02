"""Measure the sensor pipeline against the injected-fault answer key.

1. Late data: land the season in 4 arrival batches and run dbt incrementally after each one,
   then rebuild everything from scratch and check both give the same rows.
2. Duplicates: every gateway re-send must be collapsed to one reading.
3. Anomalies: precision and recall of spike and stuck-sensor flags against the answer key.
4. Degree-days: how far the season total is from the public Open-Meteo reference, cleaned vs naive.
"""
import json

import duckdb
import pandas as pd

from src.config import DUCKDB_PATH, RAW, RESULTS
from src.land import land
from src.warehouse import dbt

CUTOFFS = ["2026-06-01", "2026-08-01", "2026-09-15", None]
COMPARE = {
    "int_readings_dedup": ["device_id", "reading_ts"],
    "int_readings_flagged": ["device_id", "reading_ts"],
    "mart_pest_risk": ["orchard_id", "day"],
}
DROP = ["last_batch_id"]


def snapshot() -> dict[str, pd.DataFrame]:
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    out = {t: con.sql(f"select * from main.{t}").df().drop(columns=DROP, errors="ignore").sort_values(k).reset_index(drop=True)
           for t, k in COMPARE.items()}
    con.close()
    return out


def diff_rows(a: pd.DataFrame, b: pd.DataFrame) -> int:
    """Rows that differ in any column (floats compared to 1e-6, since sum order can change last bits)."""
    if len(a) != len(b):
        return abs(len(a) - len(b)) + min(len(a), len(b))
    bad = pd.Series(False, index=a.index)
    for col in a.columns:
        if a[col].dtype.kind == "f":
            bad |= ~((a[col] - b[col]).abs().le(1e-6) | (a[col].isna() & b[col].isna()))
        else:
            bad |= a[col].astype(str) != b[col].astype(str)
    return int(bad.sum())


def prf(pred: pd.Series, true: pd.Series) -> dict:
    tp = int((pred & true).sum()); fp = int((pred & ~true).sum()); fn = int((~pred & true).sum())
    return {"true_faults": int(true.sum()), "flagged": int(pred.sum()), "caught": tp, "false_alarms": fp, "missed": fn,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None}


def run() -> dict:
    msgs = pd.read_parquet(RAW / "sensor_messages.parquet")
    truth = pd.read_parquet(RAW / "fault_truth.parquet")

    # ---- 1. incremental runs over 4 arrival batches ----
    dbt("seed")
    batches, high_water = [], None
    for i, cutoff in enumerate(CUTOFFS):
        r = land(cutoff, reset=(i == 0))
        sec = dbt("run", "--full-refresh") if i == 0 else dbt("run")
        prev = CUTOFFS[i - 1] if i else None
        new = msgs[(msgs.arrival_ts <= pd.Timestamp(cutoff) if cutoff else True) &
                   (msgs.arrival_ts > pd.Timestamp(prev) if prev else True)]
        behind = int((new.reading_ts <= high_water).sum()) if high_water is not None else 0
        high_water = new.reading_ts.max() if high_water is None else max(high_water, new.reading_ts.max())
        batches.append({"batch": i + 1, "arrival_cutoff": cutoff or "end of season", "messages_landed": r["inserted"],
                        "messages_older_than_high_water_mark": behind, "dbt_run_seconds": round(sec, 2)})
    inc = snapshot()
    full_sec = dbt("run", "--full-refresh")
    full = snapshot()
    mismatch = {t: diff_rows(inc[t], full[t]) for t in COMPARE}
    dbt("test")

    # ---- 2. duplicates ----
    dedup = full["int_readings_dedup"]
    dup_stats = {
        "messages_received": len(msgs),
        "unique_readings_expected": len(truth),
        "unique_readings_in_warehouse": len(dedup),
        "resends_injected": int(truth.duplicates_sent.sum()),
        "resends_removed": int(dedup.duplicates_dropped.sum()),
    }

    # ---- 3. anomalies ----
    f = full["int_readings_flagged"].merge(truth, on=["device_id", "reading_ts"], how="left")
    anomalies = {
        "weather_station_readings_checked": len(f),
        "spike": prf(f.is_spike.astype(bool), f.fault.eq("spike")),
        "stuck": prf(f.is_stuck.astype(bool), f.fault.eq("stuck")),
        "any_fault": prf((f.is_spike | f.is_stuck | f.is_out_of_range).astype(bool), f.fault.ne("")),
    }

    # ---- 4. degree-days ----
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    dd = con.sql("""select orchard_id, max(cum_dd_clean) as clean_sensors, max(cum_dd_naive) as naive_average, max(cum_dd_ref) as open_meteo_reference
                    from mart_degree_days group by 1 order by 1""").df()
    pest = con.sql("""select orchard_id, any_value(mating_disruption) mating_disruption, min(biofix_date) biofix,
                         min(day) filter (where dd_since_biofix >= 100) egg_lay_window_opens,
                         min(day) filter (where dd_since_biofix >= 220) egg_hatch_window_opens,
                         max(moths_per_trap) peak_moths_per_trap
                      from mart_pest_risk group by 1 order by 1""").df()
    con.close()

    stats = {
        "late_data": {
            "batches": batches,
            "late_readings_over_1h": int((dedup.arrival_lag_min > 60).sum()),
            "full_refresh_seconds": round(full_sec, 2),
            "rows_different_incremental_vs_full_refresh": mismatch,
        },
        "duplicates": dup_stats,
        "anomalies": anomalies,
        "degree_days_season_total": dd.round(1).to_dict(orient="records"),
        "codling_moth_timing": pest.astype(str).to_dict(orient="records"),
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "pipeline_stats.json").write_text(json.dumps(stats, indent=2, default=str))
    return stats


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
