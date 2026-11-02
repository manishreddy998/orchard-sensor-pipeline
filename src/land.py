"""Land raw sensor messages in the warehouse, the way a Pub/Sub push subscription lands them.

Only messages that have *arrived* by the cutoff are loaded, so the pipeline sees late and
duplicate messages in the same order production would. Loads are idempotent: a message id
that is already landed is skipped, and every batch is written to a load manifest.
"""
import argparse
import time

import duckdb
import pandas as pd

from src.config import DUCKDB_PATH, PUBLIC, RAW


def connect():
    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DUCKDB_PATH))
    con.execute("create schema if not exists raw")
    con.execute("""create table if not exists raw.sensor_messages (
        message_id varchar, device_id varchar, reading_ts timestamp, arrival_ts timestamp,
        temperature_c double, rel_humidity_pct double, soil_vwc double, moth_count double,
        _batch_id integer, _loaded_at timestamp)""")
    con.execute("""create table if not exists raw.load_manifest (
        batch_id integer, arrival_cutoff timestamp, rows_offered integer, rows_inserted integer, loaded_at timestamp)""")
    return con


def load_weather(con):
    df = pd.read_csv(PUBLIC / "open_meteo_hourly.csv", parse_dates=["obs_hour"])
    con.execute("create or replace table raw.open_meteo_hourly as select * from df")
    return len(df)


def land(cutoff: str | None, reset: bool = False) -> dict:
    con = connect()
    if reset:
        con.execute("delete from raw.sensor_messages")
        con.execute("delete from raw.load_manifest")
    load_weather(con)
    msgs = pd.read_parquet(RAW / "sensor_messages.parquet")
    if cutoff:
        msgs = msgs[msgs.arrival_ts <= pd.Timestamp(cutoff)]
    batch_id = con.execute("select coalesce(max(batch_id), 0) + 1 from raw.load_manifest").fetchone()[0]
    before = con.execute("select count(*) from raw.sensor_messages").fetchone()[0]
    con.execute(f"""
        insert into raw.sensor_messages
        select m.*, {batch_id}, now() from msgs m
        anti join raw.sensor_messages r using (message_id)""")
    inserted = con.execute("select count(*) from raw.sensor_messages").fetchone()[0] - before
    con.execute("insert into raw.load_manifest values (?, ?, ?, ?, now())",
                [batch_id, pd.Timestamp(cutoff) if cutoff else None, len(msgs), inserted])
    con.close()
    return {"batch_id": batch_id, "offered": len(msgs), "inserted": inserted}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", help="load messages that arrived on or before this time")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    t = time.perf_counter()
    print(land(a.cutoff, a.reset), f"{time.perf_counter() - t:.2f}s")
