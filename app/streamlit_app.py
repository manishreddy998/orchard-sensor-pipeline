"""Orchard sensor pipeline dashboard: codling moth timing, sensor health, late data and the label assistant."""
import json
import sys
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.label_qa import answer  # noqa: E402

st.set_page_config(page_title="Orchard sensor pipeline", page_icon="🍏", layout="wide")


@st.cache_resource
def con():
    return duckdb.connect(str(ROOT / "data" / "orchard.duckdb"), read_only=True)


def q(sql: str) -> pd.DataFrame:
    return con().sql(sql).df()


def load(name):
    p = ROOT / "results" / name
    return json.loads(p.read_text()) if p.exists() else {}


ps, ls = load("pipeline_stats.json"), load("label_qa_stats.json")
st.title("Orchard sensor pipeline")
st.caption("In-orchard sensors → late and duplicate safe warehouse → codling moth spray timing, with answers cited from the spray label.")

c = st.columns(5)
if ps:
    c[0].metric("Sensor messages", f"{ps['duplicates']['messages_received']:,}")
    c[1].metric("Re-sends removed", f"{ps['duplicates']['resends_removed']:,} / {ps['duplicates']['resends_injected']:,}")
    a = ps["anomalies"]["any_fault"]
    c[2].metric("Bad readings caught", f"{a['caught']} / {a['true_faults']}", help=f"{a['false_alarms']} false alarm(s)")
    c[3].metric("Incremental vs full rebuild", f"{sum(ps['late_data']['rows_different_incremental_vs_full_refresh'].values())} rows differ")
if ls:
    c[4].metric("Label answers right, exact page", f"{ls['answer_correct_with_exact_page']} / {ls['answerable_questions']}",
                help=f"{ls['correct_refusals']}/{ls['unanswerable_questions']} correct refusals")

tab1, tab2, tab3, tab4 = st.tabs(["Codling moth timing", "Sensor health", "Late data", "Label assistant"])

with tab1:
    orchards = q("select distinct orchard_id from mart_pest_risk order by 1").orchard_id.tolist()
    o = st.selectbox("Orchard", orchards, index=orchards.index("ORC-OLI") if "ORC-OLI" in orchards else 0)
    df = q(f"select * from mart_pest_risk where orchard_id = '{o}' order by day")
    df["day"] = pd.to_datetime(df["day"])
    bio = pd.Timestamp(df.biofix_date.dropna().iloc[0]).date() if df.biofix_date.notna().any() else None
    md = bool(df.mating_disruption.dropna().iloc[0]) if df.mating_disruption.notna().any() else False
    st.markdown(f"**Biofix:** {bio} &nbsp;·&nbsp; **Mating disruption:** {'yes' if md else 'no'} &nbsp;·&nbsp; "
                f"**Stage at end of season:** {df.cm_stage.iloc[-1]}")
    early = df[df.day <= pd.Timestamp("2026-07-15")]
    band = pd.DataFrame([{"y": 100, "y2": 200, "label": "Egg lay: Intrepid 2F window (label PDF p.38)"},
                         {"y": 220, "y2": 250, "label": "Egg hatch: Delegate WG (label PDF p.29)"}])
    line = alt.Chart(early).mark_line(color="#2e7d32", strokeWidth=2.5).encode(
        x=alt.X("day:T", title=None), y=alt.Y("dd_since_biofix:Q", title="Degree-days (F) since biofix"))
    bands = alt.Chart(band).mark_rect(opacity=0.18).encode(y="y:Q", y2="y2:Q", color=alt.Color("label:N", legend=alt.Legend(orient="bottom", title=None),
                                                                                                   scale=alt.Scale(range=["#f9a825", "#c62828"])))
    traps = alt.Chart(early).mark_bar(color="#8d6e63", opacity=0.6).encode(
        x="day:T", y=alt.Y("moths_per_trap:Q", title="Moths per trap"))
    l, r = st.columns(2)
    l.altair_chart((bands + line).properties(height=320, title="Spray window from cleaned sensor degree-days"), use_container_width=True)
    r.altair_chart(traps.properties(height=320, title="Camera trap catches (first flight)"), use_container_width=True)
    st.dataframe(q("""select orchard_id, any_value(mating_disruption) as mating_disruption, min(biofix_date) as biofix,
                        min(day) filter (where dd_since_biofix >= 100) as egg_lay_window_opens,
                        min(day) filter (where dd_since_biofix >= 220) as egg_hatch_window_opens,
                        round(max(moths_per_trap), 1) as peak_moths_per_trap
                      from mart_pest_risk group by 1 order by 1""").astype({"biofix": str, "egg_lay_window_opens": str, "egg_hatch_window_opens": str}), hide_index=True, use_container_width=True)

with tab2:
    if ps:
        an = ps["anomalies"]
        st.dataframe(pd.DataFrame([{"fault": k, **v} for k, v in an.items() if isinstance(v, dict)]),
                     hide_index=True, use_container_width=True)
    st.subheader("Devices that need a visit")
    st.dataframe(q("""select device_id, orchard_id, device_type, readings, late_readings, late_pct,
                        duplicates_dropped, spikes, stuck_hours, max_arrival_lag_min
                      from mart_device_health order by spikes + stuck_hours desc, late_pct desc limit 15"""),
                 hide_index=True, use_container_width=True)
    dev = st.selectbox("Look at one station", q("select device_id from mart_device_health where device_type='weather_station' order by stuck_hours desc").device_id)
    f = q(f"""select reading_ts, temperature_c, case when is_spike then 'spike' when is_stuck then 'stuck' else 'ok' end as flag
              from int_readings_flagged where device_id = '{dev}' order by reading_ts""")
    first_bad = f[f.flag != "ok"].reading_ts.min()
    win = f[(f.reading_ts >= first_bad - pd.Timedelta(days=3)) & (f.reading_ts <= first_bad + pd.Timedelta(days=3))]
    st.altair_chart(alt.Chart(win).mark_circle(size=28).encode(
        x=alt.X("reading_ts:T", title=None), y=alt.Y("temperature_c:Q", title="Air temperature (C)"),
        color=alt.Color("flag:N", scale=alt.Scale(domain=["ok", "spike", "stuck"], range=["#90a4ae", "#c62828", "#f9a825"]))
    ).properties(height=300), use_container_width=True)

with tab3:
    if ps:
        st.markdown("The season is landed in 4 arrival batches. After each batch dbt runs incrementally and re-checks "
                    "a 48 hour window behind the earliest late reading. Then everything is rebuilt from scratch and compared.")
        st.dataframe(pd.DataFrame(ps["late_data"]["batches"]), hide_index=True, use_container_width=True)
        st.json(ps["late_data"]["rows_different_incremental_vs_full_refresh"])
        lag = q("""select case when arrival_lag_min <= 5 then '0-5 min' when arrival_lag_min <= 60 then '5-60 min'
                     when arrival_lag_min <= 720 then '1-12 h' when arrival_lag_min <= 1440 then '12-24 h' else '24-72 h' end as arrival_delay,
                     count(*) as readings from int_readings_dedup group by 1 order by min(arrival_lag_min)""")
        st.altair_chart(alt.Chart(lag).mark_bar(color="#2e7d32").encode(x=alt.X("arrival_delay:N", sort=None, title="How late the reading arrived"),
                                                                    y=alt.Y("readings:Q", scale=alt.Scale(type="symlog"))).properties(height=260),
                        use_container_width=True)

with tab4:
    st.markdown("Ask about a rule on the **Delegate WG**, **Intrepid 2F** or **Imidan 70-W** label (public EPA PDFs). "
                "Every answer is a word-for-word quote with its page. If the label doesn't say it, the assistant says so.")
    examples = ["What is the pre-harvest interval for Delegate WG on apples?",
                "What is the re-entry interval for Imidan 70-W on apples in British Columbia west of the Rockies?",
                "How many degree-days after biofix does codling moth egg hatch start on the Delegate WG apple label?",
                "What is the most Imidan 70-W I can apply on pears in total per year?",
                "What is the pre-harvest interval for Altacor on apples?"]
    qtext = st.selectbox("Example questions", examples)
    qtext = st.text_input("Or type your own", value=qtext)
    a = answer(qtext)
    if a.status == "answered":
        st.success(f"**{a.product} · {a.crop or 'all crops'} · PDF page {a.pdf_page}**")
        st.markdown(f"> {a.quote}")
        st.caption(f"Source: data/public/labels/{a.label_file} · quote checked on page: {'yes' if a.quote_verified else 'NO'}")
    else:
        st.warning(f"Not answered: {a.reason}.")
    if ls:
        st.caption(f"Scored on {ls['questions']} hand-labelled questions: {ls['answer_correct_with_exact_page']}/{ls['answerable_questions']} "
                   f"right with the exact page, {ls['correct_refusals']}/{ls['unanswerable_questions']} correct refusals, "
                   f"{ls['wrong_answers_given']} wrong answers.")
