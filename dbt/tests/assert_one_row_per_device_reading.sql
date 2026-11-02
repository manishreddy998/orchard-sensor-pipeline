select device_id, reading_ts, count(*) as n
from {{ ref('int_readings_dedup') }}
group by 1, 2
having count(*) > 1
