select * from {{ ref('int_readings_dedup') }} where first_arrival_ts < reading_ts
