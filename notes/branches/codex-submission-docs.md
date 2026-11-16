# codex/submission-docs

**Goal:** update the one-pager and AWS architecture against alphaforge-ai/main c172b92.
**Status:** complete and verified; ready to publish.

## Done
- Rewrote FR/EN one-pagers around the client problem, current features, four Strands agents, real AWS roles, documented evaluation and the explicit 19/100 vs 10/100 calibration limitation.
- Generated one-page A4 PDFs plus self-contained HTML previews from the Markdown sources.
- Updated AWS docs/diagrams for external Streamlit hosting, configurable regional clients/global inference profile, cache-aware calls, French extraction, deterministic fixed-income branch, independent catalogue loading, trace-storage failures and optional batch/neural speech.
- AgentCore Runtime remains explicitly not deployed; existing cache/backup operations are not falsely claimed as completed.
- Linked the printable one-pagers from both READMEs. No application logic or credentials changed.

## Decisions
- Cite c172b92 as the implementation baseline; evaluation figures retain the scope in EVALUATION.md.
- Template fidelity and deliberately injected-number tests are not presented as live-model hallucination rates.
- Diagram arrows use explicit polygons and labels use backplates for reliable SVG/PNG rendering.

## Contract changes
- None. Documentation and reproducible rendering utilities only.

## Validation
- FR and EN PDFs: exactly one A4 page each, selectable text and working app/repository links.
- Visually inspected PDF page renders and AWS diagram; no clipped text or hidden arrow labels.
- Verified Markdown links, SVG XML, source labels and PDF evidence figures; fatal lint and whitespace checks passed.
- No live AWS uptime or credentials check claimed.

## Rebuild
- python scripts/build_one_pager.py --pdf (optional ReportLab and DejaVu Sans for PDF; standard Python for HTML).
- python scripts/build_aws_diagram.py (SVG). PNG exports in this revision use PyMuPDF; SVG is the canonical vector artifact.
