"use client";

import { useEffect, useMemo, useState } from "react";

type JsonObject = Record<string, unknown>;

type CatalogModule = {
  module_id: string;
  route_prefix: string;
  paths: string[];
  request_max_bytes: number;
  result_max_bytes: number | null;
};

type Catalog = {
  catalog_version: number;
  environment: string;
  version: string;
  module_count: number;
  modules: CatalogModule[];
  catalog_digest: string;
};

type SchemaNode = {
  type?: string;
  title?: string;
  description?: string;
  properties?: Record<string, SchemaNode>;
  items?: SchemaNode;
  enum?: unknown[];
  required?: string[];
};

type Operation = {
  summary?: string;
  description?: string;
  operationId?: string;
  parameters?: Array<{
    name: string;
    in: string;
    required?: boolean;
    schema?: SchemaNode;
  }>;
  requestBody?: {
    required?: boolean;
    content?: { "application/json"?: { schema?: SchemaNode } };
  };
};

type OpenApi = {
  paths: Record<string, Record<string, Operation>>;
};

type ServiceState = "online" | "offline" | "checking";

type Account = {
  email: string;
};

const methodOrder = ["post", "get", "put", "patch", "delete"];

function sampleFromSchema(schema?: SchemaNode): unknown {
  if (!schema) return {};
  if (schema.enum?.length) return schema.enum[0];
  if (schema.type === "object" || schema.properties) {
    return Object.fromEntries(
      Object.entries(schema.properties ?? {}).map(([key, value]) => [key, sampleFromSchema(value)]),
    );
  }
  if (schema.type === "array") return [];
  if (schema.type === "boolean") return false;
  if (schema.type === "integer" || schema.type === "number") return 0;
  return "";
}

function formatBytes(value: number | null) {
  if (value === null) return "unbounded";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function shortDigest(value: string) {
  return value.replace("sha256:", "").slice(0, 12);
}

export default function ControlRoom() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [openapi, setOpenapi] = useState<OpenApi | null>(null);
  const [selectedModuleId, setSelectedModuleId] = useState("");
  const [selectedPath, setSelectedPath] = useState("");
  const [selectedMethod, setSelectedMethod] = useState("");
  const [search, setSearch] = useState("");
  const [payload, setPayload] = useState("{}");
  const [parameters, setParameters] = useState<JsonObject>({});
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [liveState, setLiveState] = useState<ServiceState>("checking");
  const [readyState, setReadyState] = useState<ServiceState>("checking");
  const [account, setAccount] = useState<Account | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [catalogResponse, openapiResponse] = await Promise.all([
          fetch("/backend/v1/deployment/catalog", { cache: "no-store" }),
          fetch("/backend/openapi.json", { cache: "no-store" }),
        ]);
        if (!catalogResponse.ok || !openapiResponse.ok) throw new Error("The API surface is unavailable.");
        const [catalogPayload, openapiPayload] = await Promise.all([
          catalogResponse.json() as Promise<Catalog>,
          openapiResponse.json() as Promise<OpenApi>,
        ]);
        setCatalog(catalogPayload);
        setOpenapi(openapiPayload);
        setSelectedModuleId(catalogPayload.modules[0]?.module_id ?? "");
        setLiveState("online");
        setReadyState("online");
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "The API surface is unavailable.");
        setLiveState("offline");
        setReadyState("offline");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  useEffect(() => {
    fetch("/api/auth/me", { cache: "no-store" })
      .then((response) => response.ok ? response.json() as Promise<{ account: Account }> : null)
      .then((data) => setAccount(data?.account ?? null))
      .catch(() => setAccount(null));
  }, []);

  const filteredModules = useMemo(() => {
    const normalized = search.trim().toLowerCase();
    return (catalog?.modules ?? []).filter(
      (module) =>
        !normalized ||
        module.module_id.toLowerCase().includes(normalized) ||
        module.paths.some((path) => path.toLowerCase().includes(normalized)),
    );
  }, [catalog, search]);

  const selectedModule = catalog?.modules.find((module) => module.module_id === selectedModuleId) ?? null;

  const operations = useMemo(() => {
    if (!selectedModule || !openapi) return [];
    return selectedModule.paths.flatMap((path) =>
      methodOrder.flatMap((method) => {
        const operation = openapi.paths[path]?.[method];
        return operation ? [{ path, method, operation }] : [];
      }),
    );
  }, [openapi, selectedModule]);

  const selectedOperation = operations.find(
    (item) => item.path === selectedPath && item.method === selectedMethod,
  ) ?? operations[0];

  useEffect(() => {
    if (!selectedOperation) return;
    setSelectedPath(selectedOperation.path);
    setSelectedMethod(selectedOperation.method);
    const schema = selectedOperation.operation.requestBody?.content?.["application/json"]?.schema;
    setPayload(JSON.stringify(sampleFromSchema(schema), null, 2));
    setParameters(
      Object.fromEntries(
        (selectedOperation.operation.parameters ?? []).map((parameter) => [parameter.name, ""]),
      ),
    );
    setResult("");
    setError("");
  }, [selectedModuleId, selectedOperation?.path, selectedOperation?.method]);

  async function execute() {
    if (!selectedOperation) return;
    setExecuting(true);
    setError("");
    setResult("");
    try {
      const unresolved = selectedOperation.operation.parameters?.filter(
        (parameter) => parameter.in === "path" && !parameters[parameter.name],
      );
      if (unresolved?.length) throw new Error(`Enter ${unresolved.map((item) => item.name).join(", ")}.`);
      const resolvedPath = selectedOperation.path.replace(/\{([^}]+)\}/g, (_, name: string) =>
        encodeURIComponent(String(parameters[name] ?? "")),
      );
      const hasBody = Boolean(selectedOperation.operation.requestBody);
      const request: RequestInit = { method: selectedOperation.method.toUpperCase() };
      if (hasBody) {
        request.headers = { "Content-Type": "application/json" };
        request.body = JSON.stringify(JSON.parse(payload));
      }
      const response = await fetch(`/backend${resolvedPath}`, request);
      const text = await response.text();
      let formatted = text;
      try {
        formatted = JSON.stringify(JSON.parse(text), null, 2);
      } catch {
        formatted = text;
      }
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}\n${formatted}`);
      setResult(formatted);
    } catch (executeError) {
      setError(executeError instanceof Error ? executeError.message : "Request failed.");
    } finally {
      setExecuting(false);
    }
  }

  return (
    <main className="shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">G</div>
          <div>
            <p className="eyebrow">AURORA / RESEARCH SYSTEMS</p>
            <h1>GLIO Proteogen</h1>
          </div>
        </div>
        <div className="topbar-right">
          <span className="environment-chip">{catalog?.environment ?? "loading"}</span>
          <a href={account ? "/console" : "/register"} className="agent-link">{account ? "Open agent console ↗" : "Register + pair ↗"}</a>
          <a href="/backend/docs" target="_blank" rel="noreferrer" className="docs-link">
            Open API docs ↗
          </a>
        </div>
      </header>

      <section className="hero-grid">
        <div className="hero-copy">
          <p className="eyebrow accent">MODEL OPERATIONS / CONTROL ROOM</p>
          <h2>Run evidence-grade model routes with context.</h2>
          <p className="hero-description">
            A focused surface for browsing mounted contracts, inspecting transport limits, and replaying typed requests against the live deployment.
          </p>
          <div className="status-row">
            <span className={`status-pill ${liveState}`}><i /> Live {liveState}</span>
            <span className={`status-pill ${readyState}`}><i /> Ready {readyState}</span>
            <span className="digest-pill">catalog {catalog ? shortDigest(catalog.catalog_digest) : "--------"}</span>
          </div>
          <div className="hero-actions">
            <a className="execute-button link-button" href={account ? "/console" : "/register"}>{account ? "Launch GLIO Agent Console" : "Create account + pair T3 Code"}<span>↗</span></a>
            <span className="hero-action-note">T3 Code runtime · one-time secure pairing</span>
          </div>
        </div>
        <div className="metric-panel">
          <div className="metric-main">
            <span className="metric-label">Mounted modules</span>
            <strong>{catalog?.module_count ?? "—"}</strong>
            <span className="metric-caption">route registry in sync</span>
          </div>
          <div className="metric-divider" />
          <div className="metric-stack">
            <span><b>API</b> v{catalog?.version ?? "—"}</span>
            <span><b>WRITE</b> typed request surfaces</span>
            <span><b>LIMITS</b> enforced at transport</span>
          </div>
        </div>
      </section>

      <section className="workspace">
        <aside className="module-rail">
          <div className="rail-heading">
            <div>
              <p className="eyebrow">DEPLOYMENT CATALOG</p>
              <h3>Modules <span>{catalog?.module_count ?? 0}</span></h3>
            </div>
            <span className="live-dot" />
          </div>
          <label className="search-box">
            <span>⌕</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search routes" />
          </label>
          <div className="module-list">
            {loading && <div className="empty-state">Loading catalog…</div>}
            {!loading && filteredModules.length === 0 && <div className="empty-state">No routes match.</div>}
            {filteredModules.map((module) => (
              <button
                className={`module-item ${module.module_id === selectedModuleId ? "selected" : ""}`}
                key={module.module_id}
                onClick={() => setSelectedModuleId(module.module_id)}
              >
                <span className="module-id">{module.module_id}</span>
                <span className="module-route-count">{module.paths.length} routes</span>
                <span className="module-arrow">›</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="route-space">
          {selectedModule ? (
            <>
              <div className="route-header">
                <div>
                  <p className="eyebrow accent">SELECTED MODULE</p>
                  <h3>{selectedModule.module_id} <span>{selectedModule.route_prefix}</span></h3>
                </div>
                <div className="limit-grid">
                  <div><span>REQUEST</span><b>{formatBytes(selectedModule.request_max_bytes)}</b></div>
                  <div><span>RESULT</span><b>{formatBytes(selectedModule.result_max_bytes)}</b></div>
                </div>
              </div>
              <div className="route-tabs">
                {operations.map((item) => (
                  <button
                    className={`route-tab ${item.path === selectedPath && item.method === selectedMethod ? "active" : ""}`}
                    key={`${item.method}-${item.path}`}
                    onClick={() => {
                      setSelectedPath(item.path);
                      setSelectedMethod(item.method);
                    }}
                  >
                    <span className={`method method-${item.method}`}>{item.method}</span>
                    <span>{item.path.replace(selectedModule.route_prefix, "") || "/"}</span>
                  </button>
                ))}
              </div>
              {selectedOperation && (
                <div className="executor-card">
                  <div className="executor-heading">
                    <div>
                      <div className="operation-line"><span className={`method method-${selectedOperation.method}`}>{selectedOperation.method}</span><code>{selectedOperation.path}</code></div>
                      <p>{selectedOperation.operation.summary ?? "Model route"} <span className="operation-id">{selectedOperation.operation.operationId}</span></p>
                    </div>
                    <button className="execute-button" onClick={() => void execute()} disabled={executing}>
                      {executing ? "Running…" : selectedOperation.operation.requestBody ? "Run request" : "Inspect route"}
                      <span>↗</span>
                    </button>
                  </div>
                  {(selectedOperation.operation.parameters ?? []).filter((parameter) => parameter.in === "path").length > 0 && (
                    <div className="parameter-strip">
                      {(selectedOperation.operation.parameters ?? []).filter((parameter) => parameter.in === "path").map((parameter) => (
                        <label key={parameter.name}><span>{parameter.name}</span><input value={String(parameters[parameter.name] ?? "")} onChange={(event) => setParameters((current) => ({ ...current, [parameter.name]: event.target.value }))} placeholder="path value" /></label>
                      ))}
                    </div>
                  )}
                  {selectedOperation.operation.requestBody && (
                    <div className="payload-layout">
                      <div className="editor-column">
                        <div className="panel-label"><span>REQUEST PAYLOAD</span><button onClick={() => setPayload("{}")}>Clear</button></div>
                        <textarea value={payload} onChange={(event) => setPayload(event.target.value)} spellCheck={false} />
                      </div>
                      <div className="schema-column">
                        <div className="panel-label"><span>SCHEMA SIGNAL</span><span className="required-label">required</span></div>
                        <div className="schema-card">
                          <div className="schema-summary"><span className="schema-icon">◇</span><div><b>application/json</b><small>typed contract body</small></div></div>
                          <div className="schema-fields">
                            {Object.keys(selectedOperation.operation.requestBody.content?.["application/json"]?.schema?.properties ?? {}).slice(0, 8).map((field) => <span key={field}>{field}</span>)}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  {(error || result) && <pre className={`response-panel ${error ? "error" : ""}`}>{error || result}</pre>}
                </div>
              )}
            </>
          ) : <div className="empty-workspace">Select a module to inspect its routes.</div>}
        </section>
      </section>
      <footer className="footer"><span>GLIO / PROTEOGEN</span><span>Research-use-only · bounded evidence processing</span><span>{catalog ? `${catalog.catalog_version}.0 catalog` : ""}</span></footer>
    </main>
  );
}
