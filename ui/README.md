# GLIO Proteogen Control Room

The UI is a typed Next.js control room for the deployed FastAPI surface. It reads the deployment catalog and OpenAPI document, renders route-specific request schemas, and proxies execution through the `/backend` rewrite.

## Run

```powershell
npm install
npm run dev
```

Set `GLIO_API_URL` when the API is not running at `http://127.0.0.1:8000`.
