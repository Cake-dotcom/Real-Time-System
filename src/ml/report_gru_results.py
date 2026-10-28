"""Render saved evaluation evidence without rerunning or tuning models."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from src.ml.train_gru_sensor_model import RESULTS


def main():
    read = lambda name: json.loads((RESULTS / name).read_text())
    report = read("test_evaluation.json")
    selection = read("selection.json")
    latency = read("pipeline_latency.json")
    folds = read("outer_group_evaluation.json")
    chosen = selection["selected"]
    lines = ["# GRU evaluation report", "",
        "Dataset: Skoltech Anomaly Benchmark (SKAB v0.9), Katser and Kozitsin (2020), "
        "https://doi.org/10.34740/KAGGLE/DSV/1693952. Pinned commit: "
        "b2c0d46c2971dcbfe71e26087b6d231998bb91c2.", "",
        "The GRU is integrated and faster/smaller in this experiment, but does **not** improve "
        "held-out accuracy, macro-F1 or anomaly recall over the refitted RF. Better PR/ROC "
        "ranking does not cancel the false-negative cost at the locked threshold.", "",
        "[Complete methodology, feature definitions, integration and commands](../../docs/gru_sensor_model.md). "
        "The original vehicle RF is preserved. Its incompatible features/classes preclude direct SKAB "
        "evaluation; the comparable baseline clones its classifier settings and refits on SKAB endpoints.", "",
        "## Dataset and selection", "",
        "Binary endpoint target: normal=0, anomalous=1. No faulty subclass, malicious attribution or "
        "synthetic augmentation. Eight physical features retain the original feature order and training-only scaling.", "",
        "Train: 33,623 windows (24,858 normal / 8,765 anomaly), 25 files / 20 overlap components. "
        "Validation: 4,863 (3,073 / 1,790), five components. Test: 5,153 (3,254 / 1,899), five components.", "",
        f"Chosen: one unidirectional GRU with {chosen['architecture']['hidden_size']} hidden units, "
        f"{chosen['window_length']} observations, dropout 0.2 and two-logit head. "
        f"Best epoch {chosen['best_epoch']}; threshold {chosen['threshold']:.2f}; "
        f"validation macro-F1 {chosen['validation_macro_f1']:.4f}. "
        "AdamW lr=0.001, weight decay=0.0001, batch=256, weighted cross-entropy, seed=42, "
        "maximum 30 epochs / patience 5, gradient clipping 1.0. Training used GTX 1650 CUDA.", "",
        "## Held-out metrics", "",
        "| Model | Accuracy | Macro-F1 | Weighted F1 | Anomaly recall | FPR | FNR | AP | PR-AUC | ROC-AUC |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, r in report["models"].items():
        values = [r['accuracy'], r['macro_f1'], r['weighted_f1'], r['classification_report']['anomalous']['recall'],
                  r['false_positive_rate'], r['false_negative_rate'], r['average_precision'],
                  r['pr_auc_trapezoidal'], r['roc_auc']]
        lines.append('| ' + name + ' | ' + ' | '.join(f'{v:.4f}' for v in values) + ' |')
    lines += ["", "AP is average precision; PR-AUC is trapezoidal area, with anomaly positive.", "",
              "| Model/class | Precision | Recall | F1 | Support |", "|---|---:|---:|---:|---:|"]
    for name, r in report["models"].items():
        for label in ["normal", "anomalous", "macro avg"]:
            c = r["classification_report"][label]
            lines.append(f"| {name}/{label} | {c['precision']:.4f} | {c['recall']:.4f} | {c['f1-score']:.4f} | {int(c['support'])} |")
    for name, r in report["models"].items():
        lines += ["", f"{name} confusion matrix, true rows / predicted columns [normal, anomalous]: `{r['confusion_matrix']}`."]
    lines += ["", "GRU produced 321 false alarms and 546 misses; RF produced 297 false alarms and 521 misses. "
        "On other/14.csv (increased-temperature experiment), GRU anomaly recall is only 0.1424 "
        "(259 of 302 missed). This localized failure and distribution shift limit practical use. "
        "No threshold or architecture was changed after seeing test results.", "",
        "## Timing and size", "",
        "CPU: i5-10300H, four cores/eight logical processors; Windows 11, Python 3.12.6, "
        "PyTorch 2.7.1+cu126. Batch one, two Torch threads, 20 warm-ups and 200 repetitions. "
        "GRU includes preprocessing/conversion; RF uses prepared endpoint features and one sklearn worker.", "",
        "| Model | CPU median ms | CPU p95 ms | Artifact bytes | Training seconds |", "|---|---:|---:|---:|---:|"]
    for name, r in report["models"].items():
        seconds = report["gru_training_seconds"] if name == "GRU" else report["rf_training_seconds"]
        lines.append(f"| {name} | {r['cpu_inference']['median_ms']:.3f} | {r['cpu_inference']['p95_ms']:.3f} | {r['artifact_bytes']} | {seconds:.2f} |")
    lines += ["", "GRU size includes weights and metadata. GRU training time is for the selected candidate, "
        "not total search/CV; per-candidate times are retained in selection.json.", "",
        "| Operation | Median ms | p95 ms |", "|---|---:|---:|"]
    for name in ["handshake", "message_verification", "application"]:
        r = latency[name]
        lines.append(f"| {name} | {r['median_ms']:.4f} | {r['p95_ms']:.4f} |")
    lines += ["", "Application benchmark: 200/200 isolated commissioned nominal candidates accepted. "
        "Signing and commissioning are outside its timer; verification, GRU, policy and scheduling "
        "are inside. Handshake timing includes sender/receiver helper work; MAC timing excludes signing. "
        "This is an overhead benchmark, not a closed-loop detection experiment. EDF uses simulation "
        "units without any conversion from measured milliseconds. No formal real-time guarantee is claimed.", "",
        "## Outer group robustness", "",
        "Outer folds hold out training components. The separate original validation split selects "
        "checkpoints/thresholds; outer labels are scoring-only. These runs do not change the final artifact.", "",
        "| Fold | GRU macro-F1 | RF macro-F1 |", "|---|---:|---:|"]
    for r in folds:
        lines.append(f"| {r['fold']} | {r['gru']['macro_f1']:.4f} | {r['rf']['macro_f1']:.4f} |")
    lines += ["", "Large inter-group variation reinforces the generalization limitation. Earlier inner "
        "diagnostics remain explicitly labelled and are not unbiased outer estimates.", "",
        "## Security and validity", "",
        "GRUHealthMonitor is the default backend. Statistical anomaly maps to anomalous_reading. "
        "Authentication, per-message MAC/replay, mandatory input validation, NIST risk policy, additional "
        "checks and EDF acceptance remain separate mandatory gates. Bounded source/session/run histories "
        "commit only on final acceptance. Cold start requires explicit trusted commissioning; "
        "distance-only vehicle messages fail closed. The dashboard exposes model, score, readiness and "
        "timing through backend audit, with an explicit RF baseline option and authenticated SKAB demo.", "",
        "Water-domain performance does not validate a vehicle replacement. Accepted-only runtime "
        "context differs from offline complete recordings after rejection. Commissioning is trusted "
        "administration, not acceptance of rejected startup messages. Checksums are not artifact "
        "signatures. Correlated windows on one rig and five held-out groups do not establish deployment safety.", "",
        "Final tests and file inventory: verification.json.", "",
        "![Precision-recall curves and confusion matrices](evaluation.png)"]
    (RESULTS / "evaluation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for name in report["models"]:
        c = read(f"{name}_precision_recall.json")
        axes[0].plot(c["recall"], c["precision"], label=name)
    axes[0].set(xlabel="Anomaly recall", ylabel="Anomaly precision", title="Held-out precision-recall", xlim=(0, 1), ylim=(0, 1.02))
    axes[0].legend(fontsize=8)
    for ax, (name, r) in zip(axes[1:], report["models"].items()):
        matrix = r["confusion_matrix"]
        ax.imshow(matrix, cmap="Blues")
        for i in range(2):
            for j in range(2):
                ax.text(j, i, str(matrix[i][j]), ha="center", va="center", color="white" if matrix[i][j] > 1800 else "black")
        ax.set(xticks=[0, 1], yticks=[0, 1], xticklabels=["Normal", "Anomaly"],
               yticklabels=["Normal", "Anomaly"], xlabel="Predicted", ylabel="Actual", title=name)
    fig.tight_layout()
    fig.savefig(RESULTS / "evaluation.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
