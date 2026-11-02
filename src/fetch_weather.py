"""Download real hourly weather and soil moisture for each orchard from the public Open-Meteo archive.

The result is cached in data/public/open_meteo_hourly.csv so CI and offline runs use the same numbers.
"""
import json
import sys
import urllib.request

import pandas as pd

from src.config import ORCHARDS, PUBLIC, SEASON_END, SEASON_START

URL = (
    "https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
    "&start_date={start}&end_date={end}&timezone=America%2FVancouver"
    "&hourly=temperature_2m,relative_humidity_2m,precipitation,soil_moisture_7_to_28cm,wind_speed_10m"
)
OUT = PUBLIC / "open_meteo_hourly.csv"


def fetch() -> pd.DataFrame:
    frames = []
    for o in ORCHARDS:
        with urllib.request.urlopen(URL.format(lat=o["lat"], lon=o["lon"], start=SEASON_START, end=SEASON_END), timeout=60) as r:
            h = json.load(r)["hourly"]
        df = pd.DataFrame(h).rename(columns={"time": "obs_hour"})
        df.insert(0, "orchard_id", o["orchard_id"])
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    if OUT.exists() and "--refresh" not in sys.argv:
        print(f"using cached {OUT}")
    else:
        df = fetch()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(OUT, index=False)
        print(f"wrote {len(df):,} hourly rows to {OUT}")
