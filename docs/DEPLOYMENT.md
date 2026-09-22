# Deployment and operations

## Topology and lifecycle

Run one Python 3.12 coordinator, an authenticated private Qdrant, and a dedicated
Docker runtime. API: 127.0.0.1:8000. Qdrant: 127.0.0.1:6333. For remote access use
an authenticated TLS reverse proxy or VPN. Do not publicly forward either service.
The supplied Colima VM has 4 GB RAM; `.env` sets one concurrent job. Add RAM before
raising concurrency.

Run `python -m investigation.cli serve` under a host process supervisor. Use one
worker; an exclusive lock rejects a second process sharing the job database.
Shutdown waits for bounded work. Configure a generous grace period (up to 45 minutes
for maximum steps/provider retries). On abrupt restart unfinished jobs become
`interrupted`; callers explicitly resubmit, avoiding hidden duplicate charges.

Administer dataset changes outside client requests. Prepare a new output directory,
update DATA_DIR, rebuild the index, restart the API. Keep old dataset/index pairs
for rollback. Startup verifies a full data hash; requests check size/mtime and
context hashes. Do not alter files during investigations.

Control the VM with `colima start --profile analytics` / `colima stop --profile analytics`.
It was not configured to start at login. Qdrant restarts with the VM unless stopped.
Stop the API before stopping the runtime. Stopping the Qdrant container preserves
its `analytics-qdrant-data` volume.

## Credentials and troubleshooting

Use environment/secret-manager values for OPENAI_API_KEY, ASSISTANT_API_TOKEN and
QDRANT_API_KEY. Never pass keys in source, command arguments or issues. Rotate the
API token by updating its secret and restarting the coordinator. Recreate Qdrant
with its new key and existing volume when rotating its credential.

This Mac's old Docker Desktop link/credential helper was broken. Homebrew Docker
and Colima restored execution. If a public pull still fails with a missing
`docker-credential-desktop`, isolate the public-download config instead of deleting
global credentials:

```sh
mkdir -p state/docker-public
docker --config state/docker-public --host "unix://${HOME}/.colima/analytics/docker.sock" pull qdrant/qdrant:v1.19.0
```

Execution continues through the explicit `colima-analytics` context.

## Monitoring, budgets, backup and retention

Monitor liveness/readiness, failed jobs, queue saturation, disk and provider spending.
Logs contain IDs/status/error types; authenticated results hold audit traces.
Readiness covers Qdrant and the sandbox image, not provider credit balance. Exhausted
credits require funding and an explicit resubmission.

Default limits: 8 actions, 6,000 output tokens/call, 80,000 cumulative model tokens,
90-second provider timeout with two SDK retries, 60-second execution and 32 KB output.
Input byte reservations are conservative. Provider project budgets are the financial
enforcement boundary. The application never buys credits or silently switches models.

Back up SQLite with its online backup API or stop the service first. Snapshot Qdrant
using supported tools; retain the matching index manifest, embedding cache and
prepared data. Test restore. Use encrypted storage and organization-specific retention;
there is no automatic deletion of old investigations in this release.

## Release acceptance

Install with `pip install --require-hashes -r requirements.lock`. Sandbox builds use
a pinned base digest and separate lock. Regenerate locks with
`uv pip compile --universal --generate-hashes` during reviewed updates; rerun tests,
dependency audit and live isolation tests. Deploy a reviewed version/tag.

Before business production use, complete funded Astra end-to-end validation,
representative accuracy acceptance, backup/restore, TLS/network setup and load tests.
These deployment-specific acceptance steps are not established by unit tests.
