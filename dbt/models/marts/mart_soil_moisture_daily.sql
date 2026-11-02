-- Daily root-zone soil moisture per orchard with a simple irrigation alert.
select r.orchard_id, cast(d.reading_ts as date) as day,
    avg(d.soil_vwc) as soil_vwc,
    min(d.soil_vwc) as soil_vwc_min,
    avg(d.soil_vwc) < 0.15 as irrigation_alert
from {{ ref('int_readings_dedup') }} d
join {{ ref('device_registry') }} r using (device_id)
where r.device_type = 'soil_probe'
group by 1, 2
