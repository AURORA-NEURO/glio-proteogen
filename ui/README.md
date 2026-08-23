# GLIO Proteogen Control Room

The UI is the GLIO Proteogen main site and agent console. It reads the deployment catalog and OpenAPI document, renders route-specific request schemas, and proxies execution through the `/backend` rewrite. The `/register` flow creates a GLIO account, establishes an HTTP-only session, and issues a short-lived T3 Code pairing credential through the server-side CLI. `/console` uses that credential to open the branded GLIO wrapper around the T3 Code runtime.

## Run

```powershell
npm install
npm run dev
```

Set `GLIO_API_URL` when the API is not running at `http://127.0.0.1:8000`.

## Account and agent configuration

The local default is suitable for the bundled development setup:

- `GLIO_AUTH_DATABASE_PATH` controls the SQLite account/session database. The default is `.data/auth.sqlite3`.
- `T3_CODE_URL` controls the T3 Code server URL. The default is `http://127.0.0.1:3773`.
- `T3_CODE_BASE_DIR` or `T3CODE_HOME` points the pairing issuer at the T3 Code data directory. The default is the current user's `.t3` directory.
- `T3_CODE_CLI` overrides the CLI executable when `npx` is not the deployment entry point.

Pairing credentials are returned only to the authenticated account session, are valid for 15 minutes, and are consumed once by T3 Code. Production deployments should put the account routes behind the platform identity provider and use a managed database with backups and secret rotation.
