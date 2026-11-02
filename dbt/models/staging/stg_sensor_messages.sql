-- One row per message as it arrived. Nothing is dropped here.
select
    message_id,
    device_id,
    cast(reading_ts as timestamp) as reading_ts,
    cast(arrival_ts as timestamp) as arrival_ts,
    date_diff('minute', cast(reading_ts as timestamp), cast(arrival_ts as timestamp)) as arrival_lag_min,
    temperature_c,
    rel_humidity_pct,
    soil_vwc,
    moth_count,
    _batch_id as batch_id,
    _loaded_at as loaded_at
from {{ source('raw', 'sensor_messages') }}
