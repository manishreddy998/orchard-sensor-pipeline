-- Daily codling moth degree-days (Fahrenheit, base 50 F, upper 88 F, horizontal cutoff from hourly data).
-- Three versions are kept so the effect of data cleaning is visible:
--   clean   trusted orchard temperature (flags removed, median of stations)
--   naive   plain average of every station, no quality checks
--   ref     public Open-Meteo reanalysis for the same location
with h as (
    select w.orchard_id, w.obs_hour, w.temperature_c, w.raw_mean_temperature_c, r.ref_temperature_c
    from {{ ref('fct_orchard_hourly_weather') }} w
    left join {{ ref('stg_reference_weather') }} r
      on r.orchard_id = w.orchard_id and r.obs_hour = w.obs_hour
),
d as (
    select
        orchard_id,
        cast(obs_hour as date) as day,
        count(*) as hours_observed,
        sum(least(greatest(temperature_c, 10.0), 31.1) - 10.0) / 24 * 1.8 as dd_clean,
        sum(least(greatest(raw_mean_temperature_c, 10.0), 31.1) - 10.0) / 24 * 1.8 as dd_naive,
        sum(least(greatest(ref_temperature_c, 10.0), 31.1) - 10.0) / 24 * 1.8 as dd_ref
    from h
    group by 1, 2
)
select *,
    sum(dd_clean) over (partition by orchard_id order by day) as cum_dd_clean,
    sum(dd_naive) over (partition by orchard_id order by day) as cum_dd_naive,
    sum(dd_ref) over (partition by orchard_id order by day) as cum_dd_ref
from d
