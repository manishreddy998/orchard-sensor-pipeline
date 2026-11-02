"""Guards on the measured results written by the evaluation step."""
import json
from pathlib import Path

import pytest

R = Path("results/pipeline_stats.json")
pytestmark = pytest.mark.skipif(not R.exists(), reason="run src.evaluate_pipeline first")


def stats():
    return json.loads(R.read_text())


def test_incremental_equals_full_refresh():
    assert all(v == 0 for v in stats()["late_data"]["rows_different_incremental_vs_full_refresh"].values())


def test_every_resend_removed():
    d = stats()["duplicates"]
    assert d["unique_readings_in_warehouse"] == d["unique_readings_expected"]
    assert d["resends_removed"] == d["resends_injected"]


def test_anomaly_recall():
    assert stats()["anomalies"]["any_fault"]["recall"] >= 0.95
