# Validation record

Validation date: 2026-09-22.

| Check | Result |
|---|---|
| Data preparation | 1,067,371 rows, stable schema and source lineage |
| Automated tests | 23 tests passed in final local release checks |
| Static checks | Ruff passed |
| Dependencies | pip-audit found no known vulnerabilities in locked dependencies |
| Runtime | Live Docker engine in dedicated Colima analytics VM |
| Isolation | Non-root, read-only source/root, blocked network, no API key/socket, output cap and timeout cleanup verified |
| Container data scan | 1,067,371 rows; 22,951 returns; 243,007 missing customer IDs; 190,616 outliers |
| Qdrant | Authenticated local server and versioned index using local BGE embeddings |
| Live API | Liveness, bearer authentication, readiness and semantic retrieval checks passed |
| Astra availability | Model metadata endpoint recognizes gpt-6-astra |
| Astra answer evaluation | Responses API returned credit_balance_exhausted; no completed answer claimed |

Tests cover preprocessing policies, invalid data, features, read-only SQL, Astra's
request contract/budgets, stale-index rejection, Qdrant embedded retrieval, bounded
repair/evidence references, API auth/input limits, queue admission, persistence,
locking and sanitized errors. Model protocol tests use test doubles; they are not
live reasoning-quality evaluations.

The full-dataset smoke check runs deterministic baseline code in a real container.
It is not represented as Astra-generated code. `scripts/live_investigation.py`
exercises the complete funded model/retrieval/code/answer path and checks computed
counts against that independent baseline. Run it after adding API credits.

Multi-tenant security, public penetration testing, high availability, recovery,
production load capacity and universal answer correctness have not been certified.
See DEPLOYMENT.md for the remaining acceptance scope.
