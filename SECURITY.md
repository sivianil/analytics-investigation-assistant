# Security boundaries

This release supports one trusted organization on a dedicated host/VM. Its bearer
token grants equal access to the registered dataset and all job results. It is not
multi-tenant. Use TLS/VPN for remote access. Loopback HTTP is for local development;
use TLS and private network restrictions for remote Qdrant.

Generated Python is untrusted. The coordinator launches a fresh container with one
read-only dataset and one read-only script. It passes no API secrets, Docker socket,
home directory, database credentials or writable host volume. It disables network
and privilege escalation, drops capabilities, bounds resources/output, enforces
timeouts and cleans up containers. Default Docker seccomp applies. No host execution
fallback exists. Colima adds a Linux VM boundary on macOS.

The trusted coordinator has Docker access. Container isolation is defense in depth,
not proof against runtime/kernel vulnerabilities. Use a dedicated host; consider
gVisor/Kata for stronger isolation. Patch the VM, Docker and image. Never mount a
Docker socket into a public frontend. Public hostile multi-tenant code execution
requires additional architecture and security acceptance.

Successful execution and evidence IDs establish provenance, not universal analytical
correctness. Review high-impact answers and use representative evaluations. Prompts
alone cannot guarantee injection resistance; OS isolation is the execution boundary.

Secrets come from environment/private `.env`. Logs omit raw questions, provider
exception bodies and credentials. Private persisted jobs contain questions, code,
answers and outputs; protect `state` with encryption/access controls and retention
policies. The LLM receives questions, retrieved context and bounded execution output.
Local embeddings keep retrieval text local; optional OpenAI embeddings send it to
that API. Prepared data, state, traces and caches are excluded from Git.

Local inference uses Ollama at a loopback-only URL, with no authentication header,
OpenAI key or environment proxy forwarded. Cloud model tags are rejected. Keep
Ollama bound to localhost; it is a trusted host service, not the untrusted-code
sandbox. Model-generated Python still runs only in Docker. Selecting the OpenAI
provider explicitly sends the question/context/evidence to that API.

The SQLAlchemy connector is trusted ingestion, requiring read-only credentials,
approved queries and server-side timeouts. Generated SQLite/Python runs only inside
the sandbox. No automatic remote database writes are available.

Report issues privately to the repository owner. Do not put keys, customer data or
live-service exploit details in public issues.
