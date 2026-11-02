-- Codling moth trap catches per orchard per day (average moths per trap).
select
    r.orchard_id,
    cast(d.reading_ts as date) as day,
    any_value(r.mating_disruption) as mating_disruption,
    count(*) as traps_reporting,
    sum(d.moth_count) as moths_total,
    avg(d.moth_count) as moths_per_trap
from {{ ref('int_readings_dedup') }} d
join {{ ref('device_registry') }} r using (device_id)
where r.device_type = 'codling_moth_trap'
group by 1, 2
