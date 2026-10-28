# Documentation index

Documentation edition: 29 October 2026. Application code, datasets, models and existing experimental results were preserved.

| Deliverable | Contents |
| --- | --- |
| [Project README](../README.md) | Setup, commands, architecture, policies, datasets, examples and limitations |
| [Presentation quick reference](Presentation_Quick_Reference.pdf) | Five pages of talking points, workflow, examples and likely questions |
| [Complete technical documentation](Complete_Technical_Documentation.pdf) | 25 pages: clickable contents, 21 chapters, implementation details and command appendix |
| [Workflow PNG](Project_Workflow_Flowchart.png) | 3840 × 2160 presentation diagram |
| [Editable Mermaid diagram](Project_Workflow_Flowchart.mmd) | Editable logical flow; exact PNG geometry is in the builder below |

## Sources and rebuilding

Keep `documentation_sources/Technical_Documentation.md`, `Quick_Reference.md`, `Command_Reference.md`, and `build_documents.py` to edit and regenerate the PDFs and PNG. The builder requires ReportLab, Pillow and the Windows Arial/Consolas fonts; these are authoring dependencies, not additions to the application's requirements. From the repository root, using an authoring environment containing these packages:

```powershell
python -B docs/documentation_sources/build_documents.py
python -B docs/documentation_sources/verify_documentation.py
```

`README.before-documentation.md` is the previous README backup. `update_readme.py` records the one-time README transformation; do not rerun it against the updated README. The Mermaid source describes the diagram independently of the Pillow renderer.

## Verification and scope

See [validation report](documentation_validation/validation_report.md), [machine-readable checks](documentation_validation/checks.json) and [PDF inspection](documentation_validation/pdf_quality.json). All 30 PDF pages were rendered and visually reviewed; both PDFs contain selectable text and clickable references. The PNG was opened and inspected.

This edition executed 24 small scheduling checks, a worked example, policy checks, syntax parsing and README link/path checks. It did not reinstall the application environment, retrain models or rerun expensive experiments. The historical 278-test pass remains in `results/repository_cleanup/tests.log`; it is not a new test run.

Keep the source files and validation JSON/report for reproducibility. Page renders and contact sheets in `documentation_validation/rendered/` are optional QA intermediates, unnecessary for running the project or reading the deliverables. No runtime changes are needed to use these documents.
