from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_editor_run_playback_export_and_reset():
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/"src/dashboard/app.py",default_timeout=60).run()
    assert not app.exception
    assert [t.label for t in app.tabs][:5]==["Simulation Setup","Live Simulation","Security and Sensor Monitoring","Results and Analysis","Algorithm Comparison"]
    next(n for n in app.number_input if n.label=="Release horizon").set_value(1.5)
    next(b for b in app.button if b.label=="Run laboratory").click().run(timeout=60)
    assert not app.exception
    result=app.session_state["lab_results"][0]
    assert result["trace"]["metrics"]["released_jobs"]==4
    assert result["trace"]["metrics"]["completed_jobs"]==4
    next(b for b in app.button if b.label=="Jump to final state").click().run()
    assert not app.exception
    assert app.session_state["lab_step"]==len(result["trace"]["snapshots"])-1
    next(b for b in app.button if b.label=="Reset laboratory").click().run()
    assert not app.exception
    assert "lab_results" not in app.session_state


def test_unit_conversion_preserves_physical_workload_and_validation():
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/"src/dashboard/app.py",default_timeout=60).run()
    next(s for s in app.selectbox if s.label=="Input time unit").select("ms").run()
    assert not app.exception
    assert app.session_state["lab_horizon"]==15000
    assert app.session_state["lab_tasks"][0]["execution"]==250
    next(b for b in app.button if b.label=="Validate workload").click().run()
    assert not app.exception and any("Valid:" in s.value for s in app.success)


def test_preset_loading_duplicate_task_and_actual_comparison():
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/"src/dashboard/app.py",default_timeout=60).run()
    next(s for s in app.selectbox if s.label=="Workload preset").select("Tampered and replayed")
    next(b for b in app.button if b.label=="Load preset").click().run()
    assert app.session_state["lab_tasks"][1]["message"]=="tampered"
    assert app.session_state["lab_events"][0]["type"]=="replay"
    next(b for b in app.button if b.label=="Duplicate task").click().run()
    assert len(app.session_state["lab_tasks"])==5
    next(s for s in app.selectbox if s.label=="Workload preset").select("Normal operation")
    next(b for b in app.button if b.label=="Load preset").click().run()
    next(s for s in app.selectbox if s.label=="Run mode").select("Compare algorithms").run()
    next(s for s in app.multiselect if s.label=="Algorithms to compare").set_value(["Standard-EDF","RA-LP-EDF"])
    next(n for n in app.number_input if n.label=="Release horizon").set_value(1.)
    next(b for b in app.button if b.label=="Run laboratory").click().run(timeout=60)
    assert not app.exception
    results=app.session_state["lab_results"]
    assert len(results)==2 and len({r["workload_id"] for r in results})==1


def test_optimized_comparison_uses_real_engine_and_two_gantts():
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/"src/dashboard/app.py",default_timeout=60).run()
    next(s for s in app.selectbox if s.label=="Run mode").select("Compare algorithms").run()
    next(s for s in app.multiselect if s.label=="Algorithms to compare").set_value(["RA-LP-EDF","RA-LP-EDF-Optimized"])
    next(n for n in app.number_input if n.label=="Release horizon").set_value(1.)
    next(b for b in app.button if b.label=="Run laboratory").click().run(timeout=60)
    assert not app.exception
    results=app.session_state["lab_results"]
    assert len({r["workload_id"] for r in results})==1
    assert any(s.value=="Original and optimized schedules" for s in app.subheader)
    optimized=next(r for r in results if r["algorithm"]=="RA-LP-EDF-Optimized")
    assert optimized["trace"]["metrics"]["completed_jobs"]==4
    assert all(m["authentication"]=="passed" for m in optimized["security"]["messages"])
    assert all("reservation" in j for snap in optimized["trace"]["snapshots"] for j in snap["jobs"])
