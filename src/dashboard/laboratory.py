"""Interactive workload designer and trace playback; no scheduling logic in UI."""
from copy import deepcopy
import json
import pandas as pd
import altair as alt
import streamlit as st
from src.lab.config import preset, PRESETS, CRITICALITIES, MESSAGE_CONDITIONS, HEALTH_CONDITIONS, EVENT_TYPES, validate
from src.lab.simulation import run, compare, csv_bytes, export_json, playback
from src.scheduler.experiments import ALGORITHMS, SCENARIOS


def reset_lab():
    for key in list(st.session_state):
        if key.startswith("lab_"): del st.session_state[key]


def load_preset():
    value=preset(st.session_state["lab_preset"])
    st.session_state["lab_tasks"]=value["tasks"]
    st.session_state["lab_events"]=value["events"]
    st.session_state["lab_revision"]=st.session_state.get("lab_revision",0)+1
    st.session_state["lab_unit"]="s"; st.session_state["lab_previous_unit"]="s"
    st.session_state["lab_horizon"]=15.
    for key in ("lab_results","lab_step"): st.session_state.pop(key,None)


def change_unit():
    old=st.session_state.get("lab_previous_unit","s"); new=st.session_state["lab_unit"]
    if old==new: return
    factor=1000 if new=="ms" else .001
    for row in st.session_state["lab_tasks"]:
        for key in ("release","execution","deadline","period","quantum"):
            if row.get(key) is not None: row[key]*=factor
        for key in ("arrivals","phases"):
            try: values=json.loads(row.get(key) or "[]")
            except (ValueError,TypeError): continue
            if key=="arrivals": values=[x*factor for x in values]
            else:
                for phase in values:
                    for field in ("execution","quantum"):
                        if field in phase: phase[field]*=factor
            row[key]=json.dumps(values) if values else ""
    for event in st.session_state["lab_events"]:
        for key in ("time","duration","repeat_every"): event[key]*=factor
    for key in ("lab_horizon","lab_dwell","lab_ttl","lab_checkpoint"):
        if key in st.session_state: st.session_state[key]*=factor
    st.session_state["lab_previous_unit"]=new
    st.session_state["lab_revision"]+=1


def display_table(rows):
    if rows: st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    else: st.caption("No records for this selection.")


def gantt(result,clock=None):
    trace=result["trace"]; factor=1000 if result["display_unit"]=="s" else 1
    rows=[]
    for interval in trace["timeline"]:
        if clock is not None and interval["start"]>clock: continue
        end=min(interval["end"],clock) if clock is not None else interval["end"]
        if end<=interval["start"]: continue
        rows.append({"job":interval["job"] or "CPU idle","start":interval["start"]/factor,"end":end/factor,
                     "mechanism":interval.get("mechanism","idle"),"phase":interval.get("phase","idle"),
                     "required":interval.get("required"),"risk":interval.get("risk")})
    jobs=[{"job":j["job_id"],"release":j["release"]/factor,"deadline":j["deadline"]/factor,"state":j["state"]} for j in trace["jobs"]]
    base=alt.Chart(pd.DataFrame(rows,columns=["job","start","end","mechanism","phase","required","risk"])).mark_bar().encode(
        x=alt.X("start:Q",title=f"Simulated time ({result['display_unit']})"),x2="end:Q",y=alt.Y("job:N",title="Job"),
        color="job:N",tooltip=["job:N","start:Q","end:Q","phase:N","mechanism:N","required:Q","risk:Q"])
    marker=alt.Chart(pd.DataFrame(jobs,columns=["job","release","deadline","state"]))
    releases=marker.mark_point(shape="triangle-right",color="#168b51",size=65).encode(x="release:Q",y="job:N",tooltip=["job:N","release:Q"])
    deadlines=marker.mark_tick(color="#c43c3c",thickness=2,size=20).encode(x="deadline:Q",y="job:N",tooltip=["job:N","deadline:Q","state:N"])
    marks=[{"job":e["job"],"time":e["time"]/factor,"event":e["event"]} for e in trace["events"]
           if e.get("job") and e["event"] in {"preempted","mechanism_switch","deadline_missed","safe_state"}
           and (clock is None or e["time"]<=clock)]
    annotations=alt.Chart(pd.DataFrame(marks,columns=["job","time","event"])).mark_point(size=85,filled=True).encode(
        x="time:Q",y="job:N",shape="event:N",color=alt.value("#222222"),tooltip=["job:N","time:Q","event:N"])
    st.altair_chart((base+releases+deadlines+annotations).interactive(),use_container_width=True)
    st.caption("Green triangles: releases. Red ticks: absolute deadlines. Black symbols: actual preemption, switch, miss or safe-state events. Bars are executed intervals, including security costs.")


def live_view(result):
    trace=result["trace"]; snaps=trace["snapshots"]
    if not snaps: st.info("Empty workload: no released jobs or playback decisions."); return
    maximum=len(snaps)-1
    st.session_state["lab_step"]=min(st.session_state.get("lab_step",0),maximum)
    cols=st.columns(3)
    if cols[0].button("Previous event",disabled=st.session_state["lab_step"]==0): st.session_state["lab_step"]-=1
    if cols[1].button("Next event",disabled=st.session_state["lab_step"]==maximum): st.session_state["lab_step"]+=1
    if cols[2].button("Jump to final state"): st.session_state["lab_step"]=maximum
    if maximum: st.slider("Playback decision",0,maximum,key="lab_step")
    snapshot=playback(result,st.session_state["lab_step"]); factor=1000 if result["display_unit"]=="s" else 1
    a,b,c=st.columns(3)
    a.metric("Simulation clock",f"t = {snapshot['time']/factor:.3f} {result['display_unit']}")
    b.metric("Actual computation",f"{result['wall_ms']:.2f} ms")
    c.metric("Safe-state events so far",snapshot["safe_state_events"])
    counts=pd.Series([j["state"] for j in snapshot["jobs"]]).value_counts().to_dict()
    st.write({"algorithm":result["algorithm"],"released_so_far":len(snapshot["jobs"]),"running":snapshot["running"],**counts})
    st.write("Next recorded event:",snapshot["next_event"] or "None")
    gantt(result,snapshot["time"])
    st.subheader("Ready queue at this decision")
    st.caption("Absolute-deadline order; criticality breaks ties. A running job can remain locked by its fixed interval or preemption cap. Table times are internal milliseconds.")
    display_table(snapshot["ready"])
    events=[e for e in trace["events"] if e["time"]<=snapshot["time"]]
    choices=[e for e in events if e["event"] in {"dispatch","preemption_forbidden","preemption_avoided","rejected","deferred","admitted","recovered"}]
    if choices: st.write("Latest scheduling decision:",choices[-1])
    st.subheader("Security and scheduling events through this time")
    display_table(events)
    job_id=st.selectbox("Inspect job",[j["job_id"] for j in trace["jobs"]])
    job=next(j for j in trace["jobs"] if j["job_id"]==job_id)
    audit=next(m for m in result["security"]["messages"] if m["job_id"]==job_id)
    st.caption("The detail below is the complete recorded outcome, including events after the playback cursor.")
    st.json({"job":job,"security_pipeline":audit,"execution":[t for t in trace["timeline"] if t["job"]==job_id],
             "events":[e for e in trace["events"] if e.get("job")==job_id]})


def monitoring_view(result):
    security=result["security"]
    st.caption("Reception → source session → MAC/replay → input/timing → health → risk policy → required checks → scheduler admission → EDF execution → deadline completion → trusted history.")
    st.caption("Authentication, health and scheduling are separate decisions. Configured anomalous/unavailable health is labelled evidence injection; normal messages use the actual selected model. No credentials are exported.")
    display_table([security["metrics"]]); display_table(security["sessions"])
    display_table(security["messages"])
    st.write("Trusted history entries:",security["trusted_history_counts"])
    risk=[{"task":task,"time_ms":p["time"],"risk":p["value"][0],"required":p["value"][1],"uncertain":p["value"][2]}
          for task,points in result["trace"]["risk_history"].items() for p in points]
    if risk:
        st.altair_chart(alt.Chart(pd.DataFrame(risk)).mark_line(interpolate="step-after",point=True).encode(
            x="time_ms:Q",y=alt.Y("risk:Q",scale=alt.Scale(domain=[0,1])),color="task:N",tooltip=list(risk[0])),use_container_width=True)
    display_table([e for e in result["trace"]["events"] if e["event"] in {"dispatch","mechanism_switch","security_suspension"}])


def results_view(result):
    trace=result["trace"]; metrics=trace["metrics"]
    a,b,c,d=st.columns(4)
    a.metric("Released jobs",metrics["released_jobs"]); b.metric("Admitted jobs",metrics["admitted_jobs"])
    c.metric("Executed jobs",metrics["executed_jobs"]); d.metric("Completed on time",metrics["completed_jobs"])
    st.caption("Miss ratios use all releases (critical ratio: all critical releases). Rejections and fail-stops are separate from deadline expiration. On-time ratio = completed / released. Null values are N/A.")
    st.caption("Residual risk is risk × (1 − assumed effectiveness), averaged over modeled execution. Compliance is execution time meeting the active policy / modeled execution time. Neither is a calibrated attack probability. CPU utilization includes all modeled costs over max(horizon, drain end).")
    display_table([{k:("N/A" if v is None else v) for k,v in metrics.items()}])
    st.subheader("Critical jobs that did not complete")
    display_table([{**j,"reason":j["transitions"][-1]["reason"]} for j in trace["jobs"] if j["critical"] and j["state"]!="completed"])
    display_table(trace["jobs"])
    gantt(result)
    st.download_button("Download complete run JSON",export_json(result),"laboratory_run.json","application/json")
    st.download_button("Download job outcomes CSV",csv_bytes(trace["jobs"]),"laboratory_jobs.csv","text/csv")
    st.download_button("Download event trace CSV",csv_bytes(trace["events"]),"laboratory_events.csv","text/csv")
    st.download_button("Download security audit CSV",csv_bytes(result["security"]["messages"]),"laboratory_security.csv","text/csv")


def comparison_view(results):
    if len(results)<2: st.info("Choose Compare algorithms in Setup and run to compare this exact workload.")
    baseline=st.selectbox("Comparison reference",[r["algorithm"] for r in results])
    reference=next(r for r in results if r["algorithm"]==baseline)["trace"]["metrics"]
    metrics=("deadline_miss_ratio","critical_deadline_miss_ratio","released_on_time_ratio","security_overhead",
             "mean_residual_risk_while_executing","security_compliance","mechanism_switches","scheduler_wall_ms",
             "pre_scheduler_rejections","admission_rejections","ever_deferred_ratio")
    rows=[]
    for r in results:
        m=r["trace"]["metrics"]; row={"algorithm":r["algorithm"],"workload_id":r["workload_id"],"wall_ms":r["wall_ms"]}
        for key in metrics:
            row[key]=m[key]; row[key+" Δ"]=m[key]-reference[key] if m[key] is not None and reference[key] is not None else None
        rows.append(row)
    display_table(rows)
    paired={r["algorithm"]:r for r in results}
    if "RA-LP-EDF" in paired and "RA-LP-EDF-Optimized" in paired:
        st.subheader("Original and optimized schedules")
        left,right=st.columns(2)
        for column,name in ((left,"RA-LP-EDF"),(right,"RA-LP-EDF-Optimized")):
            with column:
                result=paired[name]; m=result["trace"]["metrics"]
                st.write(name)
                st.metric("Critical jobs on time",f'{m["critical_completed_jobs"]}/{m["critical_jobs"]}')
                st.metric("All jobs on time",f'{m["completed_jobs"]}/{m["released_jobs"]}')
                gantt(result)
        old=paired["RA-LP-EDF"]["trace"]["metrics"]
        new=paired["RA-LP-EDF-Optimized"]["trace"]["metrics"]
        if new["critical_completed_jobs"]<old["critical_completed_jobs"]:
            st.error("This workload has fewer critical completions under the optimized policy. Inspect its safe-state and admission events before choosing it.")
        st.caption("The optimized mode reserves a compliant continuation under current evidence, selects full-cost mechanisms, and rechecks at events. Unexpected risk increases can invalidate that plan; future critical releases are not reserved in advance.")
    st.caption("All algorithms share task templates, releases, configured events and seed. Completion-dependent trusted histories can produce different later gate outcomes. EDF uses the configured checkpoint approximation; MPS is structural and SAEDF is single-CPU. Fixed-light EDF rejects protection it cannot supply.")
    st.download_button("Download comparison CSV",csv_bytes(rows),"laboratory_comparison.csv","text/csv")
    st.download_button("Download all comparison runs",export_json(results),"laboratory_comparison.json","application/json")
    st.caption("Repeated seeded workload sweeps, means, SD and paired confidence intervals remain available in the existing experiment panel below and via python -m src.scheduler.experiments --full. A manually fixed editor workload is deterministic; changing only its seed does not create new independent samples.")
    with st.expander("Repeated authenticated trials"):
        st.caption("Uses the existing random workload generator with real security gates. This generates new workloads rather than silently altering the editor's configured tasks. Up to 60 runs; inference can take several minutes.")
        seeds=st.text_input("Trial seeds",value="11,22,33",key="lab_trial_seeds")
        counts=st.multiselect("Trial task counts",[4,8,12,16,20],default=[4],key="lab_trial_counts")
        loads=st.multiselect("Trial base utilizations",[.2,.5,.75,.95],default=[.75],key="lab_trial_loads")
        scenarios=st.multiselect("Trial risk scenarios",SCENARIOS,default=["S4-spike"],key="lab_trial_scenarios")
        algorithms=st.multiselect("Trial algorithms",ALGORITHMS,default=["Standard-EDF","Static-Sec-EDF","RA-LP-EDF"],key="lab_trial_algorithms")
        if st.button("Run repeated authenticated trials"):
            try:
                from src.lab.evaluation import repeated
                with st.spinner("Executing paired trials with isolated security state…"):
                    st.session_state["lab_trials"]=repeated(seeds=tuple(int(s.strip()) for s in seeds.split(",")),
                        counts=tuple(counts),utilizations=tuple(loads),scenarios=tuple(scenarios),algorithms=tuple(algorithms))
            except ValueError as error: st.error(str(error))
        if "lab_trials" in st.session_state:
            trials=st.session_state["lab_trials"]
            display_table(trials["summary"]); display_table(trials["paired_differences"])
            st.caption(trials["method"])
            st.download_button("Export repeated trial traces",export_json(trials),"laboratory_trials.json","application/json")
            st.download_button("Export trial statistics CSV",csv_bytes(trials["summary"]),"laboratory_trials.csv","text/csv")


def show_laboratory():
    if "lab_tasks" not in st.session_state:
        initial=preset(); st.session_state["lab_tasks"]=initial["tasks"]; st.session_state["lab_events"]=initial["events"]
        st.session_state["lab_revision"]=0
    st.header("Interactive scheduling laboratory")
    st.caption("Configure a complete workload, run the existing security-gated scheduler, then replay actual decisions. Inputs use the selected unit; exported traces use milliseconds. Costs are configured estimates, not hardware WCET.")
    tabs=st.tabs(["Simulation Setup","Live Simulation","Security and Sensor Monitoring","Results and Analysis","Algorithm Comparison"])
    with tabs[0]:
        a,b,c=st.columns(3)
        a.selectbox("Workload preset",PRESETS,key="lab_preset")
        b.button("Load preset",on_click=load_preset)
        c.button("Reset laboratory",on_click=reset_lab)
        a,b,c=st.columns(3)
        unit=a.selectbox("Input time unit",["s","ms"],key="lab_unit",on_change=change_unit)
        horizon=b.number_input("Release horizon",min_value=.001,value=15.,key="lab_horizon")
        seed=c.number_input("Laboratory seed",min_value=0,value=11,step=1,key="lab_seed")
        a,b,c=st.columns(3)
        algorithm=a.selectbox("Laboratory algorithm",ALGORITHMS,index=4,key="lab_algorithm")
        st.caption("RA-LP-EDF is the preserved reference. Admission changes subset selection; Preemption avoids interruptions only when a complete-current-first bound fits. Optimized combines both with least-cost compliant protection. Compare original and optimized on the same workload; risk-spike trade-offs remain possible.")
        mode=b.selectbox("Run mode",["Single algorithm","Compare algorithms"],key="lab_mode")
        health=c.selectbox("Health backend",["RF","GRU"],key="lab_health")
        st.caption("Vehicle presets use the real RF baseline. GRU requires SKAB features and trusted commissioning context; these vehicle messages correctly fail closed under GRU. Sessions and histories are isolated per run.")
        selected=st.multiselect("Algorithms to compare",ALGORITHMS,default=list(ALGORITHMS),key="lab_compare") if mode=="Compare algorithms" else [algorithm]
        st.subheader("Task templates")
        revision=st.session_state["lab_revision"]
        columns={"criticality":st.column_config.SelectboxColumn(options=list(CRITICALITIES)),
            "kind":st.column_config.SelectboxColumn(options=["oneshot","periodic","sporadic"]),
            "message":st.column_config.SelectboxColumn(options=list(MESSAGE_CONDITIONS)),
            "health":st.column_config.SelectboxColumn(options=list(HEALTH_CONDITIONS))}
        edited=st.data_editor(pd.DataFrame(st.session_state["lab_tasks"]),num_rows="dynamic",hide_index=True,
            column_config=columns,use_container_width=True,key=f"lab_task_editor_{revision}")
        st.session_state["lab_tasks"]=edited.to_dict("records")
        st.caption("Rows are templates; jobs use task:index IDs starting at zero. Releases exactly at the horizon are excluded; released jobs drain to terminal outcomes. Deadlines are release + relative deadline. Sporadic arrivals use a JSON list; optional phases use JSON objects whose execution costs must sum to the task budget.")
        a,b=st.columns(2)
        duplicate=a.selectbox("Task to duplicate",[r.get("task_id","") for r in st.session_state["lab_tasks"]] or [""],key="lab_duplicate")
        if b.button("Duplicate task"):
            rows=st.session_state["lab_tasks"]; source=next((r for r in rows if r["task_id"]==duplicate),None)
            if source:
                new=deepcopy(source); i=1
                while f"T{i}" in {r["task_id"] for r in rows}: i+=1
                new["task_id"]=f"T{i}"; rows.append(new); st.session_state["lab_revision"]+=1; st.rerun()
        if st.button("Add task with defaults"):
            rows=st.session_state["lab_tasks"]; new=deepcopy(preset()["tasks"][-1]); i=1
            while f"T{i}" in {r["task_id"] for r in rows}: i+=1
            new.update(task_id=f"T{i}",sensor_id=f"SIM_{i}",sensor_type="generic",release=0.)
            if unit=="ms":
                for field in ("release","execution","deadline","period","quantum"): new[field]*=1000
            rows.append(new); st.session_state["lab_revision"]+=1; st.rerun()
        st.subheader("Security events and sensor conditions")
        fields=["event_id","target","type","time","duration","value","description","repeat_every","job_number"]
        table=pd.DataFrame(st.session_state["lab_events"],columns=fields)
        events=st.data_editor(table,num_rows="dynamic",hide_index=True,
            column_config={"type":st.column_config.SelectboxColumn(options=list(EVENT_TYPES))},
            use_container_width=True,key=f"lab_event_editor_{revision}")
        st.session_state["lab_events"]=events.to_dict("records")
        if st.button("Add risk event"):
            ids={e["event_id"] for e in st.session_state["lab_events"]}; i=1
            while f"E{i}" in ids: i+=1
            st.session_state["lab_events"].append(dict(event_id=f"E{i}",target=duplicate,type="risk_spike",time=0.,duration=0.,value=.9,
                description="Require stronger protection",repeat_every=0.,job_number=0))
            st.session_state["lab_revision"]+=1; st.rerun()
        st.caption("Target a Task ID or Sensor ID. Non-risk duration=0 applies to the next matching release; positive duration affects releases in that interval. Risk events persist; duration schedules return to initial exposure. repeat_every=0 means once. job_number is 1-based; 0 uses the timestamp. Replay needs an earlier completed message from the same source.")
        with st.expander("Policy and configured costs"):
            a,b,c=st.columns(3)
            low=a.number_input("Low risk threshold",.01,.98,.3,key="lab_low")
            high=b.number_input("High risk threshold",.02,.99,.7,key="lab_high")
            hysteresis=c.number_input("Risk hysteresis",0.,.29,.05,key="lab_hysteresis")
            a,b,c=st.columns(3)
            dwell=a.number_input("Downgrade dwell",min_value=0.,value=.5 if unit=="s" else 500.,key="lab_dwell")
            ttl=b.number_input("Risk evidence freshness",min_value=.001,value=30. if unit=="s" else 30000.,key="lab_ttl")
            checkpoint=c.number_input("EDF baseline checkpoint",min_value=.001,value=.05 if unit=="s" else 50.,key="lab_checkpoint")
            a,b,c=st.columns(3)
            alpha=a.number_input("Risk objective weight",0.,10.,1.,key="lab_alpha")
            beta=b.number_input("Cost objective weight",0.,10.,.15,key="lab_beta")
            gamma=c.number_input("Switch objective weight",0.,10.,.3,key="lab_gamma")
            auth=st.number_input("Mandatory per-message cost (ms)",min_value=0.,value=1.,key="lab_auth")
            st.caption("The existing policy adds 0/1/2 ms validation and 2 ms on the first verified session message. Mechanism registry transition constants are interpreted as ms. Rejected-message CPU work is measured in Python wall time, not charged to the simulated CPU.")
        raw=dict(time_unit=unit,horizon=horizon,seed=seed,algorithm=algorithm,health_backend=health,
            tasks=st.session_state["lab_tasks"],events=st.session_state["lab_events"],auth_cost_ms=auth,checkpoint=checkpoint,
            policy=dict(low=low,high=high,hysteresis=hysteresis,dwell=dwell,ttl=ttl,alpha=alpha,beta=beta,gamma=gamma))
        if st.button("Validate workload"):
            try:
                config=validate(raw); st.success(f"Valid: {len(config.tasks)} templates, {sum(len(t.releases(config.horizon)) for t in config.tasks)} releases.")
            except (ValueError,TypeError,KeyError) as error: st.error(str(error))
        if st.button("Run laboratory",type="primary"):
            try:
                if not selected: raise ValueError("Select at least one algorithm")
                with st.spinner("Executing security gates and discrete-event scheduling…"):
                    st.session_state["lab_results"]=compare(raw,selected) if mode=="Compare algorithms" else [run(raw)]
                st.session_state["lab_step"]=0
                st.success("Run complete. Inspect playback, security monitoring, results and comparison tabs.")
            except (ValueError,TypeError,KeyError) as error: st.error(f"Configuration/run rejected: {error}")
        st.download_button("Export workload configuration",json.dumps(raw,indent=2,default=str),"laboratory_configuration.json","application/json")
    results=st.session_state.get("lab_results")
    if not results:
        for tab in tabs[1:]:
            with tab: st.info("Configure a workload and select Run laboratory.")
        return
    chosen=next((r for r in results if r["algorithm"]==algorithm),results[0])
    with tabs[1]: live_view(chosen)
    with tabs[2]: monitoring_view(chosen)
    with tabs[3]: results_view(chosen)
    with tabs[4]: comparison_view(results)
