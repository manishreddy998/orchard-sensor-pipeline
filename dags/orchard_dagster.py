"""Dagster assets for the orchard sensor pipeline.

Runs hourly in production (Dagster+ or a Cloud Run job). Each asset calls the same Python
modules that CI runs, so the schedule and the tests can never drift apart.
"""
import subprocess
import sys

from dagster import (AssetExecutionContext, AssetSelection, Definitions, ScheduleDefinition, asset,
                     define_asset_job)


def _py(module: str, *args: str) -> str:
    r = subprocess.run([sys.executable, "-m", module, *args], capture_output=True, text=True, check=True)
    return r.stdout[-2000:]


@asset(group_name="ingest", description="Real hourly weather and soil moisture from the public Open-Meteo archive.")
def open_meteo_weather(context: AssetExecutionContext) -> None:
    context.log.info(_py("src.fetch_weather"))


@asset(group_name="ingest", deps=[open_meteo_weather],
       description="Sensor messages landed from the gateway feed; idempotent on message_id, logged to a load manifest.")
def raw_sensor_messages(context: AssetExecutionContext) -> None:
    context.log.info(_py("src.land"))


@asset(group_name="transform", deps=[raw_sensor_messages],
       description="dbt incremental dedup, quality flags, degree-days, trap biofix and pest risk marts, plus dbt tests.")
def dbt_orchard_models(context: AssetExecutionContext) -> None:
    context.log.info(_py("src.warehouse", "build"))


@asset(group_name="quality", deps=[dbt_orchard_models],
       description="Late-data, duplicate and anomaly scores against the injected-fault answer key.")
def pipeline_scoreboard(context: AssetExecutionContext) -> None:
    context.log.info(_py("src.evaluate_pipeline"))


@asset(group_name="quality", description="Cited label Q&A scored on the hand-labelled question set.")
def label_qa_scoreboard(context: AssetExecutionContext) -> None:
    context.log.info(_py("src.evaluate_labels"))


hourly_job = define_asset_job("orchard_hourly", selection=AssetSelection.groups("ingest", "transform"))

defs = Definitions(
    assets=[open_meteo_weather, raw_sensor_messages, dbt_orchard_models, pipeline_scoreboard, label_qa_scoreboard],
    jobs=[hourly_job],
    schedules=[ScheduleDefinition(job=hourly_job, cron_schedule="15 * * * *", execution_timezone="America/Vancouver")],
)
