# Deployment

GLIO-PROTEOGEN ships as a linked research workbench and API. The deployment is
research-use-only and does not promote any model or result to clinical use.

## One-command container deployment

```bash
docker compose up --build --detach --wait
```

The services are then available at:

- scientific workbench: <http://localhost:3000>
- API console: <http://localhost:3000/api-console>
- T3 Code agent console: <http://localhost:3773>
- API liveness: <http://localhost:8000/livez>
- API readiness: <http://localhost:8000/readyz>
- OpenAPI document: <http://localhost:8000/openapi.json>

Compose publishes these development-facing ports on `127.0.0.1` only. Put an
authenticated, TLS-terminating reverse proxy in front of explicitly remote
deployments instead of widening the default host bindings.

The UI starts only after both the API and the pinned T3 Code runtime are healthy. Its own `/healthz` probe is
independent of the API probes, so container state distinguishes an unhealthy UI
from unavailable API storage or pairing runtime. `docker compose ps` shows all three health states.

The SQLite event database is persisted in the `glio-proteogen-data` volume for
the governed event-backed lanes. UI account and session records use the separate
`glio-proteogen-ui-auth` volume. T3 Code runtime state uses the dedicated
`glio-proteogen-t3-state` volume; its internal broker issues bounded 15-minute
pairing credentials without writing them to service logs. Mounted research
analysis and replay, including the KNCC two-block factor-graph composition,
remain synchronous and stateless: requests and results are not stored in either
application database volume.

All three services run as non-root users with read-only root filesystems, dropped
Linux capabilities, `no-new-privileges`, and writable tmpfs mounts only where
the runtime requires them. The three narrowly scoped state volumes are the only
persistent writable mounts; the T3 workspace bind is read-only.

Stop the deployment without deleting its data:

```bash
docker compose down
```

Delete the persisted governed event database, UI account/session database, and
T3 runtime state only when explicitly intended:

```bash
docker compose down --volumes
```

## Reproducible backend image

The backend build uses pinned Python and uv container versions and runs
`uv sync --locked --no-dev --no-editable`. Production dependencies therefore
come from `uv.lock`; the build fails when the project metadata and lock disagree.
CI publishes the installed Python packages as a CycloneDX JSON inventory plus
the image inspection record and SHA-256 checksums of `Dockerfile` and `uv.lock`.

For traceable local image labels, provide the source revision and source epoch:

```bash
GLIO_PROTEOGEN_VCS_REF=$(git rev-parse HEAD) \
SOURCE_DATE_EPOCH=$(git show -s --format=%ct HEAD) \
docker compose build
```

## Process deployment

To run the API without containers:

```bash
export GLIO_PROTEOGEN_DATABASE_PATH=/var/lib/glio-proteogen/events.sqlite3
uv run python -m glio_proteogen.asgi
```

Supported API settings are `GLIO_PROTEOGEN_DATABASE_PATH`,
`GLIO_PROTEOGEN_HOST`, `GLIO_PROTEOGEN_PORT`, `GLIO_PROTEOGEN_LOG_LEVEL`, and
`GLIO_PROTEOGEN_ENVIRONMENT`. Log level accepts `critical`, `error`, `warning`,
`info`, `debug`, or `trace`.

## Discovery and research routes

`GET /v1/deployment/catalog` remains the compatibility catalog for governed
module routes. `GET /v2/deployment/catalog` describes mounted operations,
including all sixteen research adapters, from the live FastAPI route table. Every operation
declares its method, media types, effective limits, safety and mutability class,
and either one repository-validated example or an explicit reason why example
execution abstains. Catalog construction rejects shadow registrations, and
production application construction fails when two handlers claim the same
public method/path key.

The mounted research surface contains twelve distinct scientific-inference lanes,
one integrated KNCC factor-graph composition surface, and three compatibility
facades: sixteen adapters and sixty-four operations in total. The composition
surface reuses two exact fitted child engines and does not increase the
independent-model count. Every prefix below exposes `GET profile`, `GET demo`,
`POST analyze`, and `POST verify`:

- `/v1/research/proteogenomic-state`
- `/v1/research/gbm-proteomic-axes`
- `/v1/research/neftel-protein-programs`
- `/v1/research/gbm-master-kinases`
- `/v1/research/gbm-functional-proteotype`
- `/v1/research/gbm-rna-purity`
- `/v1/research/longitudinal-gbm`
- `/v1/research/longitudinal-gbm-phospho`
- `/v1/research/longitudinal-gbm-kinase-transition`
- `/v1/research/longitudinal-gbm-neftel-transition`
- `/v1/research/longitudinal-gbm-reactome-transition`
- `/v1/research/longitudinal-gbm-complex-transition`
- `/v1/research/gbm-factor-graph`
- `/v2/research/modules/m10/functional-proteotype`
- `/v2/research/modules/m11/protein-native-subtype`
- `/v2/research/modules/m14/microenvironment-protein-programs`

The workbench makes twelve of the thirteen computational surfaces directly visible.
The standalone longitudinal kinase-signature transition remains available
through API and CLI and is also shown as an exact nested child inside the
factor-graph view. The three compatibility facades remain API-only; neither they
nor the factor-graph composition add scientific models.

Inspect the profile before submitting work. Server limits are authoritative;
oversized, non-finite, structurally invalid, or unsupported graphs are rejected
without partial persistence. ECGI analysis requests are capped at 2 MiB, results
at 4 MiB, and replay envelopes at 7 MiB. GBM proteomic-axis analysis requests
are capped at 2 MiB, results at 1 MiB, and replay envelopes at 4 MiB. A replay
envelope carries the original request and result together. Neftel protein-program requests are
also capped at 2 MiB, results at 1 MiB, and replay envelopes at 4 MiB.
GBM master-kinase analysis requests and results are capped at 2 MiB, and replay
envelopes at 4 MiB. Longitudinal GBM requests are capped at 2 MiB, results at 4
MiB, and replay envelopes at 8 MiB. Its server deadline is 120 seconds; the UI
uses a 130-second client envelope so it can receive the backend's typed timeout
receipt instead of racing it. The KNCC/Neftel program-transition lane uses the
same 2 MiB request, 4 MiB result, 8 MiB replay-envelope, two-concurrent-computation,
and 120-second deadline bounds as the other fitted longitudinal protein lanes.
KNCC factor-graph requests are capped at 4 MiB,
results at 8 MiB, and request/result replay envelopes at 16 MiB. Each child is
limited to two through five time points, and the HTTP deadline is 120 seconds.

Most research adapters admit two concurrent HTTP computations per API process;
the KNCC factor-graph adapter admits one because each operation runs the exact
Reactome child and then the exact SPHINKS child deterministically in serial
under one whole-request 120-second deadline that also covers bounded body
reading and validation. The shipped container starts one API worker. Direct
library/CLI calls do not use the HTTP limiters, and multi-worker or replicated
deployments multiply capacity; use an external admission layer if a deployment
requires a cluster-global limit.
