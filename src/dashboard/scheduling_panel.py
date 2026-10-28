"""Views use current simulator outputs, never prefilled performance claims."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from src.scheduler.dynamic_risk import Policy
from src.scheduler.experiments import ALGORITHMS, SCENARIOS, workload, run_algorithm
from src.scheduler.security_costs import default_registry


def show_trace(trace):
    st.caption("Finite simulated workload. Configured costs are not measured WCETs or deployment guarantees.")
    st.dataframe([trace["metrics"]],hide_index=True)
    st.subheader("Jobs and deadline outcomes")
    st.dataframe(trace["jobs"],hide_index=True)
    timeline=pd.DataFrame(trace["timeline"])
    if not timeline.empty:
        import altair as alt
        plot=timeline.copy()
        plot["job"]=plot["job"].fillna("idle")
        if "mechanism" not in plot: plot["mechanism"]="idle"
        st.altair_chart(alt.Chart(plot).mark_bar().encode(
            x=alt.X("start:Q",title="Simulation time"),x2="end:Q",y="job:N",color="mechanism:N",
            tooltip=["job","start","end","mechanism"]),use_container_width=True)
    risk_rows=[{"time":point["time"],"task":task,"risk":point["value"][0],
        "minimum_level":point["value"][1],"uncertain":point["value"][2]}
        for task,points in trace["risk_history"].items() for point in points]
    if risk_rows:
        import altair as alt
        st.altair_chart(alt.Chart(pd.DataFrame(risk_rows)).mark_line(interpolate="step-after",point=True).encode(
            x="time:Q",y=alt.Y("risk:Q",scale=alt.Scale(domain=[0,1])),color="task:N",
            tooltip=["task","time","risk","minimum_level","uncertain"]),use_container_width=True)
    with st.expander("Execution, risk, admission and reservation audit"):
        st.dataframe(trace["timeline"],hide_index=True)
        st.dataframe(trace["events"],hide_index=True)
        st.json({"risk_history":trace["risk_history"],"reservations":trace["reservations"],
                 "static_analysis":trace.get("static_analysis")})


def show_experiments():
    with st.expander("Risk-aware limited-preemption scheduling laboratory"):
        st.caption("Synthetic recurring tasks, separate from authenticated live sensor messages. Baselines are explicitly bounded approximations; see docs/scheduling_design.md.")
        algorithm=st.selectbox("Research algorithm",ALGORITHMS,index=4)
        scenario=st.selectbox("Risk scenario",SCENARIOS)
        n=st.select_slider("Task count",[4,8,12,16,20],value=8)
        utilization=st.slider("Base utilization",.2,.95,.5,.05)
        seed=st.number_input("Workload seed",min_value=0,value=11,step=1)
        alpha=st.slider("Residual-risk weight",0.,3.,1.,.1)
        beta=st.slider("Overhead weight",0.,1.,.15,.05)
        if st.button("Run scheduling experiment"):
            tasks,events=workload(n,utilization,int(seed),scenario)
            policy=replace(Policy(ttl=601),alpha=alpha,beta=beta)
            st.session_state["scheduling_config"]={"seed":int(seed),"scenario":scenario,"base_utilization":utilization,
                "policy":asdict(policy),"tasks":[asdict(t) for t in tasks],
                "mechanisms":{k:asdict(m) for k,m in default_registry().items()}}
            st.session_state["scheduling_trace"]=run_algorithm(tasks,events,algorithm,
                policy=policy)
        if "scheduling_trace" in st.session_state:
            show_trace(st.session_state["scheduling_trace"])
            with st.expander("Workload and cost assumptions"):
                st.json(st.session_state["scheduling_config"])
        results=Path(__file__).resolve().parents[2]/"results/scheduling/aggregates.json"
        if results.exists() and st.checkbox("Show saved paired experiment summary"):
            rows=json.loads(results.read_text(encoding="utf-8"))
            st.dataframe([{**{k:v for k,v in row.items() if k!="metrics"},
                **{k:v["mean"] for k,v in row["metrics"].items()}} for row in rows],hide_index=True)
