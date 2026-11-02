"""Shared settings for the orchard sensor pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PUBLIC = DATA / "public"
RAW = DATA / "raw"
RESULTS = ROOT / "results"
DUCKDB_PATH = DATA / "orchard.duckdb"

SEASON_START = "2026-04-01"
SEASON_END = "2026-10-25"

# Three real Okanagan / Similkameen orchard areas (public coordinates of towns, not farms).
ORCHARDS = [
    {"orchard_id": "ORC-KEL", "name": "Kelowna block", "lat": 49.888, "lon": -119.496, "crop": "apple"},
    {"orchard_id": "ORC-OLI", "name": "Oliver block", "lat": 49.183, "lon": -119.550, "crop": "apple"},
    {"orchard_id": "ORC-CAW", "name": "Cawston block", "lat": 49.183, "lon": -119.767, "crop": "pear"},
]

# Codling moth model (public UC IPM / WSU thresholds): base 50F (10C), upper 88F (31.1C).
CM_BASE_C = 10.0
CM_UPPER_C = 31.1

# Public EPA PPLS label PDFs (downloaded from www3.epa.gov/pesticides/chem_search/ppls/).
LABELS = {
    "Delegate WG": {"file": "062719-00541-20260611.pdf", "epa_reg_no": "62719-541"},
    "Intrepid 2F": {"file": "062719-00442-20260616.pdf", "epa_reg_no": "62719-442"},
    "Imidan 70-W": {"file": "010163-00169-20250826.pdf", "epa_reg_no": "10163-169"},
}
