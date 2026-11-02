{{ config(
    materialized='incremental',
    unique_key=['device_id', 'reading_ts'],
    incremental_strategy=('merge' if target.type == 'bigquery' else 'delete+insert'),
    partition_by=({'field': 'reading_ts', 'data_type': 'timestamp', 'granularity': 'day'} if target.type == 'bigquery' else none),
    cluster_by=(['device_id'] if target.type == 'bigquery' else none)
) }}
-- Quality flags for hourly weather-station temperature.
--   out_of_range  outside the physical range for an orchard (-40 C to 50 C)
--   spike         jumps more than 6 C away from both neighbours and their average
--   stuck         part of a run of 6 or more identical values in a row
-- Late readings change their neighbours' flags, so incremental runs re-check a window that
-- starts {{ var('late_rewrite_hours') }} hours before the earliest late reading.
{% if is_incremental() %}
{% set window_sql %}
    select min(reading_ts) from {{ ref('int_readings_dedup') }}
    where last_batch_id > (select coalesce(max(last_batch_id), 0) from {{ this }})
{% endset %}
{% set res = run_query(window_sql) if execute else none %}
{% set affected_from = res.columns[0].values()[0] if res and res.columns[0].values()[0] is not none else none %}
{% endif %}
with base as (
    select d.*, r.orchard_id, r.device_type
    from {{ ref('int_readings_dedup') }} d
    join {{ ref('device_registry') }} r using (device_id)
    where r.device_type = 'weather_station'
    {% if is_incremental() %}
      {% if affected_from %}
      and d.reading_ts >= timestamp '{{ affected_from }}' - interval {{ var('late_context_hours') }} hour
      {% else %}
      and false
      {% endif %}
    {% endif %}
),
nbr as (
    select *,
        lag(temperature_c) over w as prev_t,
        lead(temperature_c) over w as next_t,
        case when temperature_c = lag(temperature_c) over w then 0 else 1 end as new_run
    from base
    window w as (partition by device_id order by reading_ts)
),
runs as (
    select *, sum(new_run) over (partition by device_id order by reading_ts rows unbounded preceding) as run_id
    from nbr
),
sized as (
    select *,
        count(*) over (partition by device_id, run_id) as run_len,
        row_number() over (partition by device_id, run_id order by reading_ts) as pos_in_run
    from runs
)
select
    device_id, orchard_id, reading_ts, temperature_c, rel_humidity_pct,
    arrival_lag_min, duplicates_dropped,
    coalesce(temperature_c < -40 or temperature_c > 50, false) as is_out_of_range,
    coalesce(abs(temperature_c - prev_t) > 6 and abs(temperature_c - next_t) > 6
        and abs(temperature_c - (prev_t + next_t) / 2) > 6, false) as is_spike,
    (run_len >= 6 and pos_in_run > 1) as is_stuck,
    last_batch_id
from sized
{% if is_incremental() and affected_from %}
where reading_ts >= timestamp '{{ affected_from }}' - interval {{ var('late_rewrite_hours') }} hour
{% endif %}
