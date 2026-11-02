-- Codling moth spray-timing signal per orchard per day.
-- Biofix = first of two days in a row with at least 1 moth per trap (sustained first catch).
-- Stage windows come straight from the public labels in data/public/labels:
--   Intrepid 2F (EPA 62719-442) PDF page 38 (printed page 36): apply at initiation of egg lay, "100 to 200 DD, base 50F, following biofix"
--   Delegate WG (EPA 62719-541) PDF page 29 (printed page 27): "egg hatch typically begins at 220 to 250 degree-days (base 50F) after biofix"
with t as (
    select *, lead(moths_per_trap) over (partition by orchard_id order by day) as next_day_moths
    from {{ ref('mart_trap_daily') }}
),
biofix as (
    select orchard_id, min(day) as biofix_date
    from t
    where moths_per_trap >= 1 and next_day_moths >= 1
    group by 1
),
dd as (
    select d.orchard_id, d.day, d.dd_clean, d.dd_naive, b.biofix_date,
        sum(case when d.day >= b.biofix_date then d.dd_clean else 0 end)
            over (partition by d.orchard_id order by d.day) as dd_since_biofix,
        sum(case when d.day >= b.biofix_date then d.dd_naive else 0 end)
            over (partition by d.orchard_id order by d.day) as dd_since_biofix_naive
    from {{ ref('mart_degree_days') }} d
    left join biofix b using (orchard_id)
)
select
    dd.*,
    tr.moths_per_trap,
    tr.mating_disruption,
    case
        when biofix_date is null or day < biofix_date then 'before biofix'
        when dd_since_biofix < 100 then 'flight started, no egg lay yet'
        when dd_since_biofix < 220 then 'egg lay (Intrepid 2F window 100-200 DD)'
        when dd_since_biofix <= 250 then 'egg hatch starting (Delegate WG 220-250 DD)'
        else 'larvae hatching, check re-treatment interval'
    end as cm_stage,
    case
        when dd_since_biofix between 100 and 250 and coalesce(tr.moths_per_trap, 0) >= 2 then 'high'
        when dd_since_biofix between 100 and 250 then 'medium'
        else 'low'
    end as spray_timing_risk
from dd
left join {{ ref('mart_trap_daily') }} tr using (orchard_id, day)
