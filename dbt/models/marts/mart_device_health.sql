-- Per-device health for the field team: uptime, late data, re-sends and quality flags.
with d as (
    select r.device_id, r.orchard_id, r.device_type,
        count(x.reading_ts) as readings,
        count(*) filter (where x.arrival_lag_min > 60) as late_readings,
        sum(x.duplicates_dropped) as duplicates_dropped,
        max(x.arrival_lag_min) as max_arrival_lag_min
    from {{ ref('device_registry') }} r
    left join {{ ref('int_readings_dedup') }} x using (device_id)
    group by 1, 2, 3
),
f as (
    select device_id,
        count(*) filter (where is_spike) as spikes,
        count(*) filter (where is_stuck) as stuck_hours
    from {{ ref('int_readings_flagged') }}
    group by 1
)
select d.*, coalesce(f.spikes, 0) as spikes, coalesce(f.stuck_hours, 0) as stuck_hours,
    round(100.0 * late_readings / nullif(readings, 0), 2) as late_pct
from d left join f using (device_id)
