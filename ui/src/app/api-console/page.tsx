"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  sampleFromSchema,
  schemaProperties,
  serializeQueryValue,
} from "@/lib/openapi";
import {
  catalogOperationKey,
  filterCatalogOperations,
  preferredRequestMediaType,
  resolveCatalogOperation,
  type OperationCatalog,
  type OperationOpenApiDocument,
} from "@/lib/operation-catalog";
import {
  isAbortError,
  publicHttpError,
  readBoundedJsonObject,
  readBoundedResponseText,
} from "@/lib/http";

const REQUEST_TIMEOUT_MS = 30_000;
const API_DOCUMENT_LIMIT_BYTES = 16 * 1024 * 1024;
const CONSOLE_RESPONSE_LIMIT_BYTES = 16 * 1024 * 1024;

type ServiceState = "online" | "degraded" | "offline" | "checking";

type Account = {
  email: string;
};

function formatBytes(value: number | null, nullLabel = "unbounded") {
  if (value === null) return nullLabel;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function shortDigest(value: string) {
  return value.replace("sha256:", "").slice(0, 12);
}

export default function ApiConsole() {
  const [catalog, setCatalog] = useState<OperationCatalog | null>(null);
  const [openapi, setOpenapi] = useState<OperationOpenApiDocument | null>(null);
  const [selectedOperationKey, setSelectedOperationKey] = useState("");
  const [search, setSearch] = useState("");
  const [payload, setPayload] = useState("{}");
  const [parameters, setParameters] = useState<Record<string, string>>({});
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [liveState, setLiveState] = useState<ServiceState>("checking");
  const [readyState, setReadyState] = useState<ServiceState>("checking");
  const [account, setAccount] = useState<Account | null>(null);
  const executionController = useRef<AbortController | null>(null);
  const executionGeneration = useRef(0);

  useEffect(() => {
    async function load() {
      try {
        const [catalogResponse, openapiResponse] = await Promise.all([
          fetch("/backend/v2/deployment/catalog", { cache: "no-store" }),
          fetch("/backend/openapi.json", { cache: "no-store" }),
        ]);
        if (!catalogResponse.ok || !openapiResponse.ok) throw new Error("The API surface is unavailable.");
        const [catalogPayload, openapiPayload] = await Promise.all([
          readBoundedJsonObject(catalogResponse, API_DOCUMENT_LIMIT_BYTES) as Promise<OperationCatalog>,
          readBoundedJsonObject(openapiResponse, API_DOCUMENT_LIMIT_BYTES) as Promise<OperationOpenApiDocument>,
        ]);
        setCatalog(catalogPayload);
        setOpenapi(openapiPayload);
        setSelectedOperationKey(catalogPayload.operations[0] ? catalogOperationKey(catalogPayload.operations[0]) : "");
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "The API surface is unavailable.");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  useEffect(() => {
    async function probe(path: "/livez" | "/readyz", setter: (state: ServiceState) => void) {
      setter("checking");
      try {
        const response = await fetch(`/backend${path}`, { cache: "no-store" });
        setter(response.ok ? "online" : path === "/readyz" ? "degraded" : "offline");
      } catch {
        setter("offline");
      }
    }
    void probe("/livez", setLiveState);
    void probe("/readyz", setReadyState);
  }, []);

  useEffect(() => {
    fetch("/api/auth/me", { cache: "no-store" })
      .then((response) => response.ok ? response.json() as Promise<{ account: Account }> : null)
      .then((data) => setAccount(data?.account ?? null))
      .catch(() => setAccount(null));
  }, []);

  const filteredOperations = useMemo(() => {
    return filterCatalogOperations(catalog?.operations ?? [], search);
  }, [catalog, search]);

  const selectedCatalogOperation = catalog?.operations.find(
    (operation) => catalogOperationKey(operation) === selectedOperationKey,
  ) ?? catalog?.operations[0] ?? null;

  const selectedOperation = useMemo(() => {
    return selectedCatalogOperation && openapi
      ? resolveCatalogOperation(selectedCatalogOperation, openapi)
      : null;
  }, [openapi, selectedCatalogOperation]);
  const selectedRequestMediaType = selectedOperation
    ? preferredRequestMediaType(selectedOperation.operation)
    : null;
  const selectedRequestSchema = selectedRequestMediaType
    ? selectedOperation?.operation.requestBody?.content?.[selectedRequestMediaType]?.schema
    : undefined;

  useEffect(() => {
    if (!selectedOperation) return;
    executionController.current?.abort();
    executionGeneration.current += 1;
    setExecuting(false);
    const requestMediaType = preferredRequestMediaType(selectedOperation.operation);
    const schema = requestMediaType
      ? selectedOperation.operation.requestBody?.content?.[requestMediaType]?.schema
      : undefined;
    const sample = sampleFromSchema(schema, openapi ?? {});
    setPayload(requestMediaType === "application/octet-stream"
      ? typeof sample === "string" ? sample : ""
      : JSON.stringify(sample, null, 2));
    setParameters(
      Object.fromEntries(
        selectedOperation.parameters.map((parameter) => {
          const sample = sampleFromSchema(parameter.schema, openapi ?? {});
          return [parameter.name, Array.isArray(sample) ? sample.join(",") : sample === null ? "" : String(sample)];
        }),
      ),
    );
    setResult("");
    setError("");
  }, [openapi, selectedOperation]);

  useEffect(() => () => executionController.current?.abort(), []);

  async function execute() {
    if (!selectedOperation) return;
    executionController.current?.abort();
    const controller = new AbortController();
    const generation = executionGeneration.current + 1;
    executionGeneration.current = generation;
    executionController.current = controller;
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, REQUEST_TIMEOUT_MS);
    setExecuting(true);
    setError("");
    setResult("");
    try {
      const unresolved = selectedOperation.parameters.filter(
        (parameter) =>
          (parameter.in === "path" || parameter.in === "query") &&
          parameter.required === true &&
          !(parameters[parameter.name] ?? "").trim(),
      );
      if (unresolved?.length) throw new Error(`Enter ${unresolved.map((item) => item.name).join(", ")}.`);
      const resolvedPath = selectedOperation.path.replace(/\{([^}]+)\}/g, (_, name: string) =>
        encodeURIComponent(String(parameters[name] ?? "")),
      );
      const query = new URLSearchParams();
      for (const parameter of selectedOperation.parameters.filter((item) => item.in === "query")) {
        for (const value of serializeQueryValue(parameters[parameter.name] ?? "", parameter.schema)) {
          query.append(parameter.name, value);
        }
      }
      const requestPath = `${resolvedPath}${query.size ? `?${query.toString()}` : ""}`;
      const hasBody = Boolean(selectedOperation.operation.requestBody);
      const request: RequestInit = {
        method: selectedOperation.catalog.method,
        cache: "no-store",
        signal: controller.signal,
      };
      if (hasBody) {
        const requestMediaType = preferredRequestMediaType(selectedOperation.operation);
        if (requestMediaType === null) throw new Error("The operation does not declare a request media type.");
        let body: string | Blob;
        if (requestMediaType === "application/json") {
          body = JSON.stringify(JSON.parse(payload));
        } else if (requestMediaType === "application/octet-stream") {
          body = new Blob([payload], { type: requestMediaType });
        } else {
          throw new Error(`The console cannot safely encode ${requestMediaType} request bodies.`);
        }
        const bodyBytes = typeof body === "string" ? new Blob([body]).size : body.size;
        if (
          selectedOperation.catalog.request_max_bytes !== null &&
          bodyBytes > selectedOperation.catalog.request_max_bytes
        ) throw new Error("The request exceeds this operation's declared transport limit.");
        request.headers = { "Content-Type": requestMediaType };
        request.body = body;
      }
      const response = await fetch(`/backend${requestPath}`, request);
      const responseLimit = Math.min(
        selectedOperation.catalog.result_max_bytes ?? CONSOLE_RESPONSE_LIMIT_BYTES,
        CONSOLE_RESPONSE_LIMIT_BYTES,
      );
      const text = await readBoundedResponseText(response, responseLimit);
      if (!response.ok) throw publicHttpError(response, text);
      if (generation !== executionGeneration.current || controller.signal.aborted) return;
      let formatted = text;
      try {
        formatted = JSON.stringify(JSON.parse(text), null, 2);
      } catch {
        formatted = text;
      }
      setResult(formatted);
    } catch (executeError) {
      if (generation !== executionGeneration.current) return;
      if (isAbortError(executeError)) {
        setError(timedOut ? "Request timed out after 30 seconds." : "Request cancelled.");
      } else {
        setError(executeError instanceof Error ? executeError.message : "Request failed.");
      }
    } finally {
      window.clearTimeout(timeout);
      if (generation === executionGeneration.current) {
        if (executionController.current === controller) executionController.current = null;
        setExecuting(false);
      }
    }
  }

  function cancelExecution() {
    executionController.current?.abort();
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
          <a href="/" className="agent-link">Research workbench ↗</a>
          <a href={account ? "/console" : "/register"} className="agent-link">{account ? "Agent console ↗" : "Register + pair ↗"}</a>
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
            <span className="metric-label">Mounted operations</span>
            <strong>{catalog?.operation_count ?? "—"}</strong>
            <span className="metric-caption">OpenAPI registry in sync</span>
          </div>
          <div className="metric-divider" />
          <div className="metric-stack">
            <span><b>API</b> v{catalog?.version ?? "—"}</span>
            <span><b>CATALOG</b> operation schema v{catalog?.catalog_version ?? "—"}</span>
            <span><b>SAFETY</b> route-specific policy</span>
          </div>
        </div>
      </section>

      <section className="workspace">
        <aside className="module-rail">
          <div className="rail-heading">
            <div>
              <p className="eyebrow">DEPLOYMENT CATALOG</p>
              <h3>Operations <span>{catalog?.operation_count ?? 0}</span></h3>
            </div>
            <span className="live-dot" />
          </div>
          <label className="search-box">
            <span>⌕</span>
            <input
              aria-label="Search operation catalog"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search operations"
            />
          </label>
          <div className="module-list">
            {loading && <div className="empty-state">Loading catalog…</div>}
            {!loading && filteredOperations.length === 0 && <div className="empty-state">No operations match.</div>}
            {filteredOperations.map((operation) => {
              const key = catalogOperationKey(operation);
              const method = operation.method.toLowerCase();
              return (
                <button
                  aria-label={key}
                  className={`module-item ${key === selectedOperationKey ? "selected" : ""}`}
                  key={key}
                  onClick={() => setSelectedOperationKey(key)}
                >
                  <span className={`method method-${method}`}>{method}</span>
                  <span className="operation-rail-copy">
                    <b>{operation.operation_id}</b>
                    <small>{operation.path}</small>
                  </span>
                  <span className="module-arrow">›</span>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="route-space">
          {selectedCatalogOperation ? (
            <>
              <div className="route-header">
                <div>
                  <p className="eyebrow accent">SELECTED OPERATION</p>
                  <h3>{selectedCatalogOperation.operation_id} <span>{selectedCatalogOperation.method} {selectedCatalogOperation.path}</span></h3>
                </div>
                <div className="limit-grid">
                  <div><span>REQUEST LIMIT</span><b>{formatBytes(selectedCatalogOperation.request_max_bytes, "no body")}</b></div>
                  <div><span>RESULT LIMIT</span><b>{formatBytes(selectedCatalogOperation.result_max_bytes)}</b></div>
                </div>
              </div>
              <div className="catalog-metadata" aria-label="Operation catalog metadata">
                <div><span>SAFETY CLASS</span><b>{selectedCatalogOperation.safety_class}</b></div>
                <div><span>MUTABILITY</span><b>{selectedCatalogOperation.mutability_class}</b></div>
                <div><span>EXAMPLE STATUS</span><b>{selectedCatalogOperation.validated_example_status}</b></div>
                <div>
                  <span>{selectedCatalogOperation.validated_example_status === "validated" ? "VALIDATED EXAMPLE" : "ABSTENTION REASON"}</span>
                  <b>{selectedCatalogOperation.validated_example_id ?? selectedCatalogOperation.validated_example_abstention_reason ?? "invalid metadata"}</b>
                </div>
                <div><span>TAGS</span><b>{selectedCatalogOperation.tags.join(", ") || "none"}</b></div>
                <div><span>REQUEST MEDIA</span><b>{selectedCatalogOperation.request_media_types.join(", ") || "none"}</b></div>
                <div><span>RESPONSE MEDIA</span><b>{selectedCatalogOperation.response_media_types.join(", ") || "none"}</b></div>
                <div><span>PARAMETERS</span><b>{selectedCatalogOperation.parameter_locations.join(", ") || "none"}</b></div>
              </div>
              {selectedOperation && (
                <div className="executor-card">
                  <div className="executor-heading">
                    <div>
                      <div className="operation-line"><span className={`method method-${selectedOperation.method}`}>{selectedOperation.method}</span><code>{selectedOperation.path}</code></div>
                      <p>{selectedOperation.operation.summary ?? selectedOperation.catalog.summary ?? "Model route"} <span className="operation-id">{selectedOperation.operation.operationId ?? selectedOperation.catalog.operation_id}</span></p>
                    </div>
                    <button className="execute-button" onClick={executing ? cancelExecution : () => void execute()}>
                      {executing ? "Cancel request" : selectedOperation.operation.requestBody ? "Run request" : "Inspect route"}
                      <span>↗</span>
                    </button>
                  </div>
                  {selectedOperation.parameters.filter((parameter) => parameter.in === "path" || parameter.in === "query").length > 0 && (
                    <div className="parameter-strip">
                      {selectedOperation.parameters.filter((parameter) => parameter.in === "path" || parameter.in === "query").map((parameter) => (
                        <label key={`${parameter.in}-${parameter.name}`}><span>{parameter.name} · {parameter.in}{parameter.required ? " · required" : ""}</span><input value={parameters[parameter.name] ?? ""} onChange={(event) => setParameters((current) => ({ ...current, [parameter.name]: event.target.value }))} placeholder={`${parameter.in} value`} /></label>
                      ))}
                    </div>
                  )}
                  {selectedOperation.operation.requestBody && (
                    <div className="payload-layout">
                      <div className="editor-column">
                        <div className="panel-label"><span>REQUEST PAYLOAD</span><button onClick={() => setPayload(selectedRequestMediaType === "application/json" ? "{}" : "")}>Clear</button></div>
                        <textarea aria-label="Request payload JSON" value={payload} onChange={(event) => setPayload(event.target.value)} spellCheck={false} />
                      </div>
                      <div className="schema-column">
                        <div className="panel-label"><span>SCHEMA SIGNAL</span><span className="required-label">required</span></div>
                        <div className="schema-card">
                          <div className="schema-summary"><span className="schema-icon">◇</span><div><b>{selectedRequestMediaType ?? "undeclared"}</b><small>{selectedRequestMediaType === "application/octet-stream" ? "bounded raw UTF-8 bytes" : "typed contract body"}</small></div></div>
                          <div className="schema-fields">
                            {Object.keys(schemaProperties(selectedRequestSchema, openapi ?? {})).slice(0, 8).map((field) => <span key={field}>{field}</span>)}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  {(error || result) && <pre className={`response-panel ${error ? "error" : ""}`}>{error || result}</pre>}
                </div>
              )}
              {!selectedOperation && !loading && (
                <div className="empty-workspace">This catalog operation is missing from the current OpenAPI document.</div>
              )}
            </>
          ) : <div className="empty-workspace">Select an operation to inspect its route.</div>}
        </section>
      </section>
      <footer className="footer"><span>GLIO / PROTEOGEN</span><span>Research-use-only · bounded evidence processing</span><span>{catalog ? `v${catalog.catalog_version} operation catalog` : ""}</span></footer>
    </main>
  );
}
