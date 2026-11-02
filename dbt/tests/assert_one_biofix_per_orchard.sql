select orchard_id from {{ ref('mart_pest_risk') }}
group by 1 having count(distinct biofix_date) > 1
