"""Generate realistic in-orchard sensor messages on top of real Open-Meteo weather.

Device types (one message per reading, like a field gateway publishing to Pub/Sub):
  WX  weather station: air temperature (C) and relative humidity (%) every hour
  SM  soil moisture probe: volumetric water content (m3/m3) every hour
  CMT codling moth camera trap: moths counted since the last report, once a day at 06:00

Real-world faults are injected and written to an answer key so the pipeline can be scored:
  duplicate  the gateway re-sends a message it already sent (same reading, new message id)
  late       a device loses signal for 6 to 72 hours, then flushes its backlog at once
  spike      a single impossible jump in temperature (bad ADC read)
  stuck      a sensor repeats the same value for 8 to 36 hours (frozen firmware)
"""
import numpy as np
import pandas as pd

from src.config import CM_BASE_C, CM_UPPER_C, ORCHARDS, PUBLIC, RAW

SEED = 42
DUP_RATE = 0.03
SPIKE_RATE = 0.0025
MATING_DISRUPTION = {"ORC-KEL": True, "ORC-OLI": False, "ORC-CAW": True}


def _registry() -> pd.DataFrame:
    rows = []
    for o in ORCHARDS:
        code = o["orchard_id"].split("-")[1]
        for i in range(1, 5):
            rows.append((f"WX-{code}-{i:02d}", o["orchard_id"], "weather_station", "2025-03-15"))
        for i in range(1, 4):
            rows.append((f"SM-{code}-{i:02d}", o["orchard_id"], "soil_probe", "2025-03-15"))
        for i in range(1, 6):
            rows.append((f"CMT-{code}-{i:02d}", o["orchard_id"], "codling_moth_trap", "2026-03-20"))
    df = pd.DataFrame(rows, columns=["device_id", "orchard_id", "device_type", "installed_on"])
    df["mating_disruption"] = df["orchard_id"].map(MATING_DISRUPTION)
    return df


def _daily_dd_f(temps: pd.Series) -> pd.Series:
    """Hourly horizontal-cutoff degree-days (F) summed per day."""
    c = temps.clip(lower=CM_BASE_C, upper=CM_UPPER_C) - CM_BASE_C
    return c.groupby(temps.index.date).sum() / 24 * 1.8


def generate() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    wx = pd.read_csv(PUBLIC / "open_meteo_hourly.csv", parse_dates=["obs_hour"])
    reg = _registry()
    msgs, truth = [], []

    for o in ORCHARDS:
        w = wx[wx.orchard_id == o["orchard_id"]].set_index("obs_hour").sort_index()
        # --- weather stations and soil probes ---
        for dev in reg[(reg.orchard_id == o["orchard_id"]) & (reg.device_type != "codling_moth_trap")].itertuples():
            n = len(w)
            if dev.device_type == "weather_station":
                offset = rng.normal(0, 0.6)
                temp = w.temperature_2m.values + offset + rng.normal(0, 0.25, n)
                rh = np.clip(w.relative_humidity_2m.values + rng.normal(0, 2.0, n), 1, 100)
                vwc = np.full(n, np.nan)
            else:
                temp = np.full(n, np.nan)
                rh = np.full(n, np.nan)
                vwc = np.clip(w.soil_moisture_7_to_28cm.values * rng.uniform(0.85, 1.15) + rng.normal(0, 0.004, n), 0.01, 0.6)
            fault = np.array([""] * n, dtype=object)
            if dev.device_type == "weather_station":
                # spikes
                idx = rng.choice(n, int(n * SPIKE_RATE), replace=False)
                temp[idx] = temp[idx] + rng.choice([-1, 1], len(idx)) * rng.uniform(15, 30, len(idx))
                fault[idx] = "spike"
                # one or two stuck episodes on most stations
                for _ in range(rng.integers(1, 3)):
                    start, length = rng.integers(200, n - 50), rng.integers(8, 37)
                    temp[start:start + length] = temp[start]
                    fault[start + 1:start + length] = "stuck"
            ts = w.index
            arrival = ts + pd.to_timedelta(rng.integers(5, 240, n), unit="s")
            # connectivity loss episodes: backlog flushed when signal comes back
            late = np.zeros(n, dtype=bool)
            for _ in range(rng.integers(2, 5)):
                start, length = rng.integers(0, n - 80), rng.integers(6, 73)
                end = min(start + length, n)
                arrival = arrival.where(~((np.arange(n) >= start) & (np.arange(n) < end)), ts[end - 1] + pd.Timedelta(minutes=7))
                late[start:end] = True
            df = pd.DataFrame({
                "device_id": dev.device_id, "reading_ts": ts, "arrival_ts": arrival,
                "temperature_c": np.round(temp, 2), "rel_humidity_pct": np.round(rh, 1), "soil_vwc": np.round(vwc, 4),
                "moth_count": np.nan,
            })
            msgs.append(df)
            truth.append(pd.DataFrame({"device_id": dev.device_id, "reading_ts": ts, "fault": fault, "late": late}))

        # --- codling moth traps (daily count at 06:00) ---
        dd = _daily_dd_f(w.temperature_2m).cumsum()
        days = pd.to_datetime(dd.index)
        md = 0.3 if MATING_DISRUPTION[o["orchard_id"]] else 1.0
        # overwintering flight centred ~250 DD-F after Apr 1, summer flight ~1350 DD-F
        expected = md * (6 * np.exp(-((dd.values - 260) / 110) ** 2) + 9 * np.exp(-((dd.values - 1350) / 230) ** 2))
        for dev in reg[(reg.orchard_id == o["orchard_id"]) & (reg.device_type == "codling_moth_trap")].itertuples():
            count = rng.poisson(expected * rng.uniform(0.7, 1.3))
            ts = days + pd.Timedelta(hours=6)
            df = pd.DataFrame({"device_id": dev.device_id, "reading_ts": ts,
                               "arrival_ts": ts + pd.to_timedelta(rng.integers(30, 900, len(ts)), unit="s"),
                               "temperature_c": np.nan, "rel_humidity_pct": np.nan, "soil_vwc": np.nan,
                               "moth_count": count.astype(float)})
            msgs.append(df)
            truth.append(pd.DataFrame({"device_id": dev.device_id, "reading_ts": ts, "fault": "", "late": False}))

    m = pd.concat(msgs, ignore_index=True)
    # gateway re-sends: exact duplicate payload arriving a little later
    dup = m.sample(frac=DUP_RATE, random_state=SEED).copy()
    dup["arrival_ts"] = dup["arrival_ts"] + pd.to_timedelta(rng.integers(60, 7200, len(dup)), unit="s")
    m = pd.concat([m, dup], ignore_index=True).sample(frac=1, random_state=SEED).reset_index(drop=True)
    m.insert(0, "message_id", [f"msg-{i:07d}" for i in range(len(m))])
    t = pd.concat(truth, ignore_index=True)
    t["duplicates_sent"] = 0
    dkey = dup.groupby(["device_id", "reading_ts"]).size()
    t = t.set_index(["device_id", "reading_ts"])
    t.loc[dkey.index, "duplicates_sent"] = dkey.values
    return m, t.reset_index(), reg


if __name__ == "__main__":
    m, t, reg = generate()
    RAW.mkdir(parents=True, exist_ok=True)
    m.to_parquet(RAW / "sensor_messages.parquet", index=False)
    t.to_parquet(RAW / "fault_truth.parquet", index=False)
    reg.to_csv("dbt/seeds/device_registry.csv", index=False)
    print(f"messages {len(m):,} | unique readings {len(t):,} | duplicates {int(t.duplicates_sent.sum()):,} | "
          f"late {int(t.late.sum()):,} | spikes {(t.fault=='spike').sum():,} | stuck {(t.fault=='stuck').sum():,}")
