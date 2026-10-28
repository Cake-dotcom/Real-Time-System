"""Run demonstration presets and a small paired authenticated experiment."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import json
from src.lab.config import PRESETS,preset
from src.lab.simulation import run,compare,export_json,csv_bytes
from src.lab.evaluation import repeated


def main(output):
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for name in PRESETS:
        result=run(preset(name))
        slug=name.lower().replace(" ","_")
        (output/f"{slug}.json").write_bytes(export_json(result))
        (output/f"{slug}_jobs.csv").write_bytes(csv_bytes(result["trace"]["jobs"]))
        (output/f"{slug}_events.csv").write_bytes(csv_bytes(result["trace"]["events"]))
        rows.append({"preset":name,**result["trace"]["metrics"]})
        print(name,result["trace"]["metrics"]["completed_jobs"],"completed",flush=True)
    comparison=compare(preset("Security versus performance"))
    (output/"comparison.json").write_bytes(export_json(comparison))
    trials=repeated()
    (output/"trials.json").write_bytes(export_json(trials))
    (output/"trial_statistics.csv").write_bytes(csv_bytes(trials["summary"]))
    (output/"preset_metrics.csv").write_bytes(csv_bytes(rows))
    lines=["# Authenticated laboratory demonstration results","",
        "Actual runs through production authentication/health gates and the existing scheduler. Configured costs use milliseconds; RF is the vehicle baseline.","",
        "| Preset | Released | Completed | Gate rejected | Admission rejected | Missed deadlines | Safe-state events |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['preset']} | {r['released_jobs']} | {r['completed_jobs']} | {r['pre_scheduler_rejections']} | {r['admission_rejections']} | {r['deadline_misses']} | {r['safe_state_events']} |")
    lines += ["","## Same-workload algorithm comparison","",
        "Security versus performance preset: same releases/events and seed; differing outcomes may change subsequent trusted histories.","",
        "| Algorithm | Released on time | Security overhead (ms) | Mean residual risk | Policy-relative compliance |",
        "|---|---:|---:|---:|---:|"]
    for r in comparison:
        m=r["trace"]["metrics"]
        lines.append(f"| {r['algorithm']} | {m['released_on_time_ratio']} | {m['security_overhead']:.3f} | {m['mean_residual_risk_while_executing']} | {m['security_compliance']} |")
    lines += ["","## Repeated seeded trials","",trials["method"],"",
        "Three distinct seeds, 4 tasks, nominal base utilization .75, S4-spike, 3 algorithms, 9 runs. Each trace, source hash and configuration is saved in trials.json.","",
        "| Algorithm | On-time mean | Sample SD | Approximate normal 95% CI |","|---|---:|---:|---|"]
    for r in trials["summary"]:
        m=r["metrics"]["released_on_time_ratio"]
        lines.append(f"| {r['algorithm']} | {m['mean']:.4f} | {m['std']:.4f} | {m['ci95_normal']} |")
    lines += ["","No hardware WCET, calibrated attack probability, infinite-horizon guarantee or uniform superiority is inferred. Rejected jobs are not counted as deadline misses. Structural MPS and single-CPU SAEDF are approximations. See docs/laboratory.md.",""]
    (output/"report.md").write_text("\n".join(lines),encoding="utf-8")
    print("Wrote",output/"report.md",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--output",default="results/laboratory")
    main(parser.parse_args().output)
