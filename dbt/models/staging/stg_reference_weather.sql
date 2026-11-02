select
    orchard_id,
    cast(obs_hour as timestamp) as obs_hour,
    temperature_2m as ref_temperature_c,
    relative_humidity_2m as ref_rel_humidity_pct,
    precipitation as ref_precip_mm,
    soil_moisture_7_to_28cm as ref_soil_vwc
from {{ source('raw', 'open_meteo_hourly') }}
