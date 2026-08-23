# Deployment

The supported production process is the ASGI application served by Uvicorn. It is
research-use-only and does not promote a model to clinical use.

## Container deployment

```bash
docker compose up --build -d
curl http://localhost:8000/livez
curl http://localhost:8000/readyz
```

The SQLite event database is persisted in the `glio-proteogen-data` volume. The
container is non-root, read-only apart from that volume, and exposes `/livez` for
liveness. The container healthcheck uses `/readyz`, which verifies append-only
event-chain readiness before the instance is considered healthy.

`GET /v1/deployment/catalog` returns the mounted model route prefixes, concrete
paths, and request/result byte ceilings. It is suitable for deployment smoke
tests and includes a deterministic `catalog_digest` for the mounted surface; it
does not expose the database path or other process configuration. The process
fails during startup if a registered route limit has no mounted route, preventing
deployment with an incomplete model surface.
The current catalog contains 54 mounted, route-limited module families: the 38
canonical newer model APIs listed below, the deployed M27-02 lineage lane, and
the historical production lanes.
It also reports `unmounted_route_limit_prefixes`; a production deployment must
keep that list empty.

## Process deployment

```bash
export GLIO_PROTEOGEN_DATABASE_PATH=/var/lib/glio-proteogen/events.sqlite3
uv run python -m glio_proteogen.asgi
```

Supported settings are `GLIO_PROTEOGEN_DATABASE_PATH`, `GLIO_PROTEOGEN_HOST`,
`GLIO_PROTEOGEN_PORT`, `GLIO_PROTEOGEN_LOG_LEVEL`, and
`GLIO_PROTEOGEN_ENVIRONMENT`. Log level accepts `critical`, `error`, `warning`,
`info`, `debug`, or `trace`. The application creates the database parent
directory before opening SQLite and retains the existing strict request-size,
canonical JSON, and readiness checks.

## Deployed model APIs

The canonical production process exposes the concrete model routes directly;
they are not limited to standalone test applications. The currently deployed
model surfaces are M15-05, M23-01/02/03/04/05/07/08,
M24-02/03/04/05/06/07/08, M25-01/02/03/04/05/06/07/08, M26-01 through M26-08,
M27-03 through M27-08, and M28-04. Their schema, validation,
execution/publication, and replay routes retain the paths and
contract-specific request/result ceilings defined by each module. M23-06,
M24-01, M27-01, and M28-01/02/03/05/06/07/08 remain intentionally provisional
because their upstream contracts are not present in this checkout.
