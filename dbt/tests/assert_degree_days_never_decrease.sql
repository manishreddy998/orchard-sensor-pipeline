select * from (
    select orchard_id, day, cum_dd_clean,
        lag(cum_dd_clean) over (partition by orchard_id order by day) as prev
    from {{ ref('mart_degree_days') }}
) where cum_dd_clean < prev
