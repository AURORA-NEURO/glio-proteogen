# GLIO Proteogen Research Workbench

The home route is the research-use-only scientific workbench for twelve visible
lanes (twelve of thirteen computational surfaces): GLIO-ECGI evidence graphs, the
seven published GBM proteomic-axis
ensembles, Neftel-derived bulk-protein programs, SPHINKS-derived GBM
master-kinase signature concordance, Migliozzi functional-proteotype
concordance, the published GBMPurity primary-IDH-wildtype-GBM RNA model, and
source-fitted PDC000514 protein, PDC000515 phosphosite, and KNCC Reactome V97
conditional primary-to-recurrent concordance models, the 28-participant-set
KNCC Reactome complex-transition model, the fitted eight-program KNCC/Neftel
conditional-transition model, plus the KNCC GBM factor-graph
composition/presentation surface. The factor graph preserves the
Reactome protein and longitudinal SPHINKS phosphosite children as independent
source-cohort result blocks, executes them deterministically in sequence, and
renders their 41-node / 39-edge annotation-only containment topology without
cross-modal fusion or any additional fitted inference. The standalone
longitudinal kinase-transition child remains API/CLI-only outside that composed
view. Each visible mode loads a
versioned synthetic demo, validates editable structured input, visualizes support
and uncertainty, permits cancellation and receipt download, and invokes backend
deterministic replay. The PDC lanes remain fail-closed source-cohort concordance
models; they do not claim tumor evolution, phosphosite occupancy, cross-assay
fusion, prognosis, or clinical validity.
The Reactome lane reports one global recurrence coordinate and ten pathway
coordinates conditional on that global axis, with separate unadjusted values,
uncertainty, held-gene reconstruction, contributions, and structural
ablations. These are not pathway activity or flux. PI3K/AKT has no unique
fixed-panel member, is always marked overlap-confounded, and cannot receive
fully supported status.
The KNCC/Neftel transition view reports one global and eight exact Table S2
conditional bulk-protein coordinates with measurement/source uncertainty and
structural ablations. The fitted dictionary did not beat equal marker
membership, so the UI rejects any receipt that elevates a global or program
coordinate above `LIMITED`. These coordinates are not single-cell states or
cell fractions.
The complex-transition view reports missing-aware fitted participant-set
factors without relabeling them as physical assembly, biochemical activity, or
stoichiometry.
The RNA lane emits one published-model malignant-cell-fraction estimate and
never represents it as histology, immune composition, or calibrated clinical
truth.
The original catalog/OpenAPI request runner remains available at `/api-console`;
it resolves composed and referenced schemas and supports path and query
parameters.

All backend calls use the same-origin `/backend` rewrite. `/healthz` reports UI container health, while the workbench independently probes backend `/livez` and `/readyz`.

## Run

```powershell
npm ci
npm run dev
```

Set `GLIO_API_URL` when the API is not running at `http://127.0.0.1:8000`.

## Verify

```powershell
npm run typecheck
npm run test:coverage
npm run build
npx playwright install chromium
npm run test:e2e
```

The multi-stage `Dockerfile` emits the Next.js standalone server as an unprivileged user on port 3000.

For a clean GLIO T3 workspace, create a dedicated runtime and register this repository before starting the server:

```powershell
$glioT3Home = "$env:LOCALAPPDATA\Temp\glio-proteogen-t3"
npx --yes t3@0.0.35 project add "$pwd" --title "GLIO Proteogen" --base-dir $glioT3Home
npx --yes t3@0.0.35 serve --port 3773 --base-dir $glioT3Home --no-browser
```

Start the Next.js site with the same runtime path:

```powershell
$env:T3_CODE_BASE_DIR = $glioT3Home
$env:T3_CODE_URL = "http://127.0.0.1:3773"
npm run dev -- --hostname 127.0.0.1 --port 3000
```

## Account and agent configuration

The local default is suitable for the bundled development setup:

- `GLIO_AUTH_DATABASE_PATH` controls the SQLite account/session database. The default is `.data/auth.sqlite3`.
- `T3_CODE_URL` controls the T3 Code server URL. The default is `http://127.0.0.1:3773`.
- `T3_CODE_BASE_DIR` or `T3CODE_HOME` points the pairing issuer at the T3 Code data directory. The default is the current user's `.t3` directory.
- `T3_CODE_CLI` overrides the CLI executable when `npx` is not the deployment entry point.
- `T3_PAIRING_BROKER_URL` routes issuance through the bounded internal broker used by Compose. When unset, local development invokes the exactly pinned `t3@0.0.35` package runner.

Pairing credentials are returned only to the authenticated account session, are valid for 15 minutes, and are consumed once by T3 Code. Session cookies are scoped to `/api`, so the `/backend` proxy never receives them. Production deployments should put the account routes behind the platform identity provider and use a managed database with backups and secret rotation.
