import { createServer } from "node:http";

const port = 3775;
let issueCount = 0;
let failNext = false;

function respond(response, status, payload) {
  response.writeHead(status, {
    "Cache-Control": "no-store",
    "Content-Type": "application/json; charset=utf-8",
  });
  response.end(JSON.stringify(payload));
}

async function readBody(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 4096) throw new Error("request_too_large");
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

createServer(async (request, response) => {
  if (request.method === "GET" && request.url === "/healthz") {
    respond(response, 200, { status: "ready" });
    return;
  }
  if (request.method === "POST" && request.url === "/control/fail-next") {
    failNext = true;
    respond(response, 200, { ok: true });
    return;
  }
  if (request.method === "POST" && request.url === "/pairing") {
    if (failNext) {
      failNext = false;
      respond(response, 503, { error: "pairing_unavailable" });
      return;
    }
    try {
      const body = await readBody(request);
      if (typeof body.label !== "string" || body.label.length < 1 || body.label.length > 120) {
        respond(response, 400, { error: "invalid_label" });
        return;
      }
      issueCount += 1;
      respond(response, 201, {
        credential: `e2e-opaque-pairing-${issueCount.toString().padStart(4, "0")}`,
        expiresAt: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
        label: body.label,
      });
    } catch {
      respond(response, 400, { error: "invalid_request" });
    }
    return;
  }
  if (request.method === "GET" && request.url?.startsWith("/pair")) {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end("<!doctype html><title>T3 fixture</title><p>Pairing accepted.</p>");
    return;
  }
  respond(response, 404, { error: "not_found" });
}).listen(port, "127.0.0.1");
