"""Validate saved evaluation integrity and render a reproducible Markdown report."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics


def report(directory):
    directory=Path(directory)
    read=lambda name:json.loads((directory/f"{name}.json").read_text(encoding="utf-8"))
    rows=read("raw"); sensitivity=read("sensitivity"); metadata=read("metadata")
    aggregates=read("aggregates"); paired=read("paired")
    assert len(rows)==metadata["main_runs"] and len(sensitivity)==metadata["sensitivity_runs"]
    assert all(hashlib.sha256(Path(k).read_bytes()).hexdigest()==v for k,v in metadata["source_sha256"].items()), "Evaluated source changed"
    by_workload=defaultdict(set)
    for row in rows:
        by_workload[row["config_id"]].add(row["algorithm"])
    assert all(len(v)==5 for v in by_workload.values()), "Unpaired algorithms"
    assert all(r["security_compliance"] in (1,None) for r in rows+sensitivity)
    assert all(r["reservation_violations"]==0 for r in rows+sensitivity)
    for path in directory.glob("trace_*.json"):
        trace=json.loads(path.read_text(encoding="utf-8"))
        for job in trace["jobs"]:
            if job["state"]=="completed": assert job["finish"]<=job["deadline"]+1e-8
        busy=sum(t["end"]-t["start"] for t in trace["timeline"] if t["job"])
        assert abs(busy-sum(sum(j["costs"].values()) for j in trace["jobs"]))<1e-6
    lines=["# Measured scheduler evaluation", "",
        f"{len(rows):,} main runs, {len(sensitivity)} sensitivity/ablation runs, {len(by_workload)} paired workloads.",
        f"Seeds: {metadata['seeds']}. Main-grid worker concurrency: {metadata['workers']}.",
        "Simulation units and assumed effectiveness; no hardware WCET or attack probability is measured.",
        "Source hashes, pairing, recorded compliance, reservation counters and representative trace accounting verified.",
        "", "## Representative fixed configuration: 8 tasks, base utilization 0.75", "",
        "Values are means ± sample SD across five seeds. Completion denominator includes all released jobs.",
        "Risk is conditioned on modeled execution, so read it alongside completion. Low risk is not necessarily best performance.",
        "", "| Scenario | Algorithm | Released on time | Security overhead | Mean residual risk | Critical failures / rejections |",
        "|---|---|---:|---:|---:|---:|"]
    def formatted(values):
        values=[v for v in values if v is not None]
        return "undefined" if not values else f"{statistics.mean(values):.4f} ± {statistics.stdev(values):.4f}"
    for scenario in ["S1-low","S4-spike","S7-overload"]:
        for algorithm in ["Standard-EDF","Static-Sec-EDF","MPS-LP-EDF-structural","SAEDF-style","RA-LP-EDF"]:
            group=[r for r in rows if r["scenario"]==scenario and r["n"]==8 and r["utilization"]==.75 and r["algorithm"]==algorithm]
            lines.append(f"| {scenario} | {algorithm} | "+" | ".join(formatted([r[k] for r in group]) for k in
                ["released_on_time_ratio","security_overhead","mean_residual_risk_while_executing"])+
                f" | {sum(r['critical_failed_jobs'] for r in group)} / {sum(r['critical_rejected_jobs'] for r in group)} |")
    lines += ["", "## Paired differences at the same configuration", "",
        "RA-LP-EDF minus each baseline; approximate normal 95% confidence interval over paired seed differences.",
        "Positive completion is favorable; negative overhead is favorable. Five repeats are exploratory.",
        "", "| Scenario | Baseline | Completion difference [CI] | Overhead difference [CI] |", "|---|---|---:|---:|"]
    for row in paired:
        if row["n"]!=8 or row["utilization"]!=.75 or row["scenario"] not in {"S1-low","S4-spike","S7-overload"}: continue
        values=[]
        for metric in ["released_on_time_ratio","security_overhead"]:
            m=row["metrics"][metric]; lo,hi=m["ci95_normal"]
            values.append(f"{m['mean']:.4f} [{lo:.4f}, {hi:.4f}]")
        lines.append(f"| {row['scenario']} | {row['baseline']} | {' | '.join(values)} |")
    lines += ["", "## Ablations and sensitivity", "",
        "All use S6-multiple, n=8, base utilization .75, the same five seeds. Workload changes are saved explicitly.",
        "No-admission and no-reservation runs are diagnostic ablations, not recommended timing policies.", "",
        "| Variant | Released on time | Security overhead | Safe-state events | Decision wall ms |",
        "|---|---:|---:|---:|---:|"]
    for variant in dict.fromkeys(r["variant"] for r in sensitivity):
        group=[r for r in sensitivity if r["variant"]==variant]
        lines.append(f"| {variant} | "+" | ".join(formatted([r[k] for r in group]) for k in
            ["released_on_time_ratio","security_overhead","safe_state_events","scheduler_wall_ms"])+" |")
    lines += ["", "## Interpretation limits", "",
        "The proposed policy trades assumed residual risk against overhead; it is not uniformly superior to strongest protection.",
        "Sudden risk can cause intentional fail-stop of a protected job already inside a weaker atomic interval.",
        "That failure is visible and must not be presented as preserving every critical deadline. Admission uses released demand only.",
        "Recorded execution compliance against each run's active policy is 1 in every nonempty measured run and reservation violations are zero; these are finite simulator observations, not security proofs.",
        "The no_dynamic ablation ignores new threat evidence: its policy-relative compliance and residual-risk metric cannot establish compliance with the changing external scenario. Its higher completion is not a safe security improvement.",
        "Standard EDF and Static-Sec-EDF use 1-unit checkpoints. MPS is structural and SAEDF is a single-CPU approximation.",
        "Hardware deployment, global optimality, faithful published-baseline superiority and infinite dynamic schedulability remain unproved.",
        "", "## Artifacts and commands", "",
        "`raw.json`, `workloads.json`, `aggregates.json`, `paired.json`, `sensitivity.json`, `metadata.json` and 35 representative traces retain the evidence.",
        "", "```powershell", ".\\.venv\\Scripts\\python.exe -u -m src.scheduler.experiments --full --workers 4",
        ".\\.venv\\Scripts\\python.exe scripts/report_scheduling.py", "```", "",
        "![Completion by load for 8-task scenarios](completion_by_load.png)", ""]
    (directory/"evaluation_report.md").write_text("\n".join(lines),encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(15,4.5),sharey=True)
    for ax,scenario in zip(axes,["S1-low","S4-spike","S7-overload"]):
        for algorithm in ["Standard-EDF","Static-Sec-EDF","MPS-LP-EDF-structural","SAEDF-style","RA-LP-EDF"]:
            group=sorted([r for r in aggregates if r["n"]==8 and r["scenario"]==scenario and r["algorithm"]==algorithm],key=lambda r:r["utilization"])
            x=[r["utilization"] for r in group]; y=[r["metrics"]["released_on_time_ratio"]["mean"] for r in group]
            ax.plot(x,y,marker="o",label=algorithm,linewidth=2 if algorithm=="RA-LP-EDF" else 1)
        ax.set_title(scenario); ax.set_xlabel("Base utilization (security excluded)"); ax.grid(alpha=.25); ax.set_ylim(0,1.05)
    axes[0].set_ylabel("Completed / all released jobs")
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="lower center",ncol=3,fontsize=9)
    fig.suptitle("Finite simulation: 8 tasks, mean of 5 paired seeds (variability in report)")
    fig.tight_layout(rect=(0,.15,1,.95)); fig.savefig(directory/"completion_by_load.png",dpi=160); plt.close(fig)
    print(f"Validated {len(rows)+len(sensitivity)} runs; wrote {directory / 'evaluation_report.md'}")


if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--results",default="results/scheduling")
    report(parser.parse_args().results)
