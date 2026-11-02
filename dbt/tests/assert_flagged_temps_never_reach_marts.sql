-- A trusted orchard temperature must never be built from a spike or stuck value.
select w.orchard_id, w.obs_hour
from {{ ref('fct_orchard_hourly_weather') }} w
join {{ ref('int_readings_flagged') }} f
  on f.orchard_id = w.orchard_id and f.reading_ts = w.obs_hour
where (f.is_spike or f.is_stuck) and w.stations_flagged = 0
