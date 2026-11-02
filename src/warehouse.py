"""Thin wrapper to run dbt against the local DuckDB file (or BigQuery when WAREHOUSE_TARGET=bigquery)."""
import os
import subprocess
import sys
import time

from src.config import DUCKDB_PATH, ROOT


def dbt(*args: str) -> float:
    env = {**os.environ, "DUCKDB_PATH": str(DUCKDB_PATH)}
    t = time.perf_counter()
    r = subprocess.run(["dbt", *args, "--profiles-dir", ".", "--project-dir", "."],
                       cwd=ROOT / "dbt", env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-4000:], r.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"dbt {' '.join(args)} failed")
    return time.perf_counter() - t


if __name__ == "__main__":
    print(f"{dbt(*sys.argv[1:]):.1f}s")
