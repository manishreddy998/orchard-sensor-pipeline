-- One trusted temperature per orchard per hour: the median of stations that passed every check.
select
    orchard_id,
    reading_ts as obs_hour,
    median(temperature_c) filter (where not (is_spike or is_stuck or is_out_of_range)) as temperature_c,
    median(temperature_c) as raw_median_temperature_c,
    avg(temperature_c) as raw_mean_temperature_c,
    count(*) as stations_reporting,
    count(*) filter (where is_spike or is_stuck or is_out_of_range) as stations_flagged
from {{ ref('int_readings_flagged') }}
group by 1, 2
