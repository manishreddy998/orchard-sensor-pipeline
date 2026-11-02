{{ config(
    materialized='incremental',
    unique_key=['device_id', 'reading_ts'],
    incremental_strategy=('merge' if target.type == 'bigquery' else 'delete+insert'),
    partition_by=({'field': 'reading_ts', 'data_type': 'timestamp', 'granularity': 'day'} if target.type == 'bigquery' else none),
    cluster_by=(['device_id'] if target.type == 'bigquery' else none)
) }}
-- One row per (device, reading time). Gateway re-sends are collapsed to the first copy that arrived.
-- On incremental runs only keys touched by newly landed batches are rebuilt.
with msgs as (
    select * from {{ ref('stg_sensor_messages') }}
    {% if is_incremental() %}
    where (device_id, reading_ts) in (
        select device_id, reading_ts from {{ ref('stg_sensor_messages') }}
        where batch_id > (select coalesce(max(last_batch_id), 0) from {{ this }})
    )
    {% endif %}
),
ranked as (
    select *,
        row_number() over (partition by device_id, reading_ts order by arrival_ts, message_id) as rn,
        count(*) over (partition by device_id, reading_ts) as copies_received,
        max(batch_id) over (partition by device_id, reading_ts) as last_batch_id
    from msgs
)
select
    device_id, reading_ts, arrival_ts as first_arrival_ts, arrival_lag_min,
    temperature_c, rel_humidity_pct, soil_vwc, moth_count,
    copies_received, copies_received - 1 as duplicates_dropped, last_batch_id
from ranked
where rn = 1
