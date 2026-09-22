# Validation record

Validation date: 2026-09-22.

| Check | Result |
|---|---|
| Data preparation | 1,067,371 rows, stable schema and source lineage |
| Automated tests | 31 tests passed in final local release checks |
| Static checks | Ruff passed |
| Dependencies | pip-audit found no known vulnerabilities in locked dependencies |
| Runtime | Live Docker engine in dedicated Colima analytics VM |
| Isolation | Non-root, read-only source/root, blocked network, no API key/socket, output cap and timeout cleanup verified |
| Container data scan | 1,067,371 rows; 22,951 returns; 243,007 missing customer IDs; 190,616 outliers |
| Qdrant | Authenticated local server and versioned index using local BGE embeddings |
| Live API | Liveness, bearer authentication, readiness and semantic retrieval checks passed |
| Local model | Ollama qwen3.5:4b generated and executed Python against the full dataset |
| Live Qwen counts | All four counts matched the independent baseline; 37.34 seconds |
| Live Qwen period comparison | Acceptance failed: wrong output key, incorrect narrative arithmetic and unsupported currency symbol; not validated for unattended complex reasoning |
| Astra availability | Model metadata endpoint recognizes gpt-6-astra |
| Astra answer evaluation | Responses API returned credit_balance_exhausted; no completed answer claimed |

Tests cover preprocessing policies, invalid data, features, read-only SQL, Astra's
request contract/budgets, stale-index rejection, Qdrant embedded retrieval, bounded
repair/evidence references, API auth/input limits, queue admission, persistence,
locking and sanitized errors. Protocol tests use test doubles; separate live evaluations exercise the real local model.
Local tests also cover structured output, context/token limits and rejection of remote
or cloud Ollama endpoints.

The full-dataset smoke check runs deterministic baseline code in a real container.
It is not represented as Astra-generated code. `scripts/live_investigation.py`
exercises the complete model/retrieval/code/answer path and checks computed counts
against that independent baseline. It completed successfully with local Qwen, without
API credits. Generated code streamed every row and summed existing flags; aggregate
summary counts were excluded from retrieved context. Small models can still generate
incorrect analysis; these checks validate specific questions, not universal accuracy.

Multi-tenant security, public penetration testing, high availability, recovery,
production load capacity and universal answer correctness have not been certified.
See DEPLOYMENT.md for the remaining acceptance scope.

The period-comparison trial repaired an initial Python syntax error and returned
computed period totals, but used `net_signed_line_value` instead of the requested
`net` key. Its final prose also misstated the 2011 sales-to-net gap and introduced
a dollar symbol despite unspecified currency. Successful execution/evidence IDs
do not establish that every narrative claim is correct. Review complex answers
against execution output before business use. `scripts.live_comparison` is an
acceptance probe and currently fails for this recorded local-model trial.
