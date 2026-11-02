import pytest

dagster = pytest.importorskip("dagster")


def test_assets_and_schedule_load():
    from dags.orchard_dagster import defs
    keys = {k.to_user_string() for k in defs.resolve_asset_graph().get_all_asset_keys()}
    assert {"open_meteo_weather", "raw_sensor_messages", "dbt_orchard_models",
            "pipeline_scoreboard", "label_qa_scoreboard"} <= keys
    assert defs.resolve_job_def("orchard_hourly") is not None
    sched = defs.resolve_schedule_def("orchard_hourly_schedule")
    assert sched.cron_schedule == "15 * * * *"
