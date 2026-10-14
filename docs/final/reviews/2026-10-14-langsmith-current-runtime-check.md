# LangSmith current runtime check

Read-only verification against final @ bd9e8769 and backend port 8000/PID 1889. CodeGraph reported up to date (208 files, 3551 nodes, 10850 edges) with earlier-engine warning; index-coverage tool unavailable, coverage UNKNOWN. Relevant current source returned/read. No application fix, new workflow command, cloud trace write, database mutation, reset or server restart performed.

- Health: {"status": "ok", "mode": "LIVE", "python": "3.12.13", "platform": "Darwin", "live_ready": true, "langsmith_ready": true, "langsmith_enabled": true, "langsmith_export_errors": 0}
- Configured project: `invoice-referee` (`97168b16-9ee9-4485-9ff0-35642aea1c4b`); observed cloud run count: 91, spans included.
- Exact local case: `case:44c8b533cb4e5212beff`; default database currently has this draft, version 2.
- Exact cloud operation: `settlement-draft-read` / `c05f5d6c-c0b3-5209-87de-e170a64cbf65`, matches local case via metadata.
- Local time: 2026-10-14T18:57:26.658207+07:00 → 2026-10-14T18:58:19.789254+07:00; no cloud error on sampled operation/spans.
- Retrieved 10 runs for this trace, including operation and OCR/classify/extract/validate/match children.
- [Direct cloud run](https://smith.langchain.com/o/6290bb7f-942c-4bbf-a501-58c5a46a1220/projects/p/97168b16-9ee9-4485-9ff0-35642aea1c4b/r/c05f5d6c-c0b3-5209-87de-e170a64cbf65?poll=true)
- Raw sanitized evidence: `.runtime/langsmith-check-20261014-195823/readback.json`.

The current workflow is exporting traces, unlike the earlier M0-only review. The user's active LangSmith account/workspace, browser filters, and viewed URL were not inspected; an exact UI cause remains unverified. The local case is DRAFT, so this check proves document-read telemetry, not a completed financial submission for this case. Span export happens at operation exit, so an in-progress read is not expected to have live step streaming in this implementation.
