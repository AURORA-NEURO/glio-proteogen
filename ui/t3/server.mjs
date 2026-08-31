import { spawn } from "node:child_process";
import { createServer } from "node:http";
import path from "node:path";
import process from "node:process";

const baseDirectory = process.env.T3_CODE_BASE_DIR ?? "/data/t3";
const workspaceDirectory = process.env.T3_WORKSPACE_PATH ?? "/workspace";
const publicUrl = (process.env.T3_CODE_PUBLIC_URL ?? "http://127.0.0.1:3773").replace(/\/$/, "");
const t3Port = Number.parseInt(process.env.T3_CODE_PORT ?? "3773", 10);
const brokerPort = Number.parseInt(process.env.T3_PAIRING_BROKER_PORT ?? "3774", 10);
const cliPath = path.join(process.cwd(), "node_modules", "t3", "dist", "bin.mjs");
const maximumBodyBytes = 4096;
const maximumOutputBytes = 100_000;
const commandTimeoutMilliseconds = 30_000;
const childEnvironment = { ...process.env, T3CODE_HOME: baseDirectory };

function runCli(arguments_, { allowExistingProject = false } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [cliPath, ...arguments_], {
      cwd: workspaceDirectory,
      env: childEnvironment,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let output = "";
    let errorOutput = "";
    let complete = false;
    const finish = (callback) => {
      if (complete) return;
      complete = true;
      clearTimeout(timer);
      callback();
    };
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      finish(() => reject(new Error("T3 command timed out")));
    }, commandTimeoutMilliseconds);
    child.stdout?.on("data", (chunk) => {
      output += chunk.toString();
      if (Buffer.byteLength(output, "utf8") > maximumOutputBytes) {
        child.kill("SIGTERM");
        finish(() => reject(new Error("T3 command output exceeded its bound")));
      }
    });
    child.stderr?.on("data", (chunk) => {
      errorOutput += chunk.toString();
      if (Buffer.byteLength(errorOutput, "utf8") > maximumOutputBytes) {
        child.kill("SIGTERM");
        finish(() => reject(new Error("T3 command error output exceeded its bound")));
      }
    });
    child.once("error", () => finish(() => reject(new Error("T3 command failed to start"))));
    child.once("close", (code) => finish(() => {
      if (code === 0 || (allowExistingProject && `${output}\n${errorOutput}`.includes("ProjectAlreadyExistsError"))) resolve(output);
      else reject(new Error("T3 command failed"));
    }));
  });
}

async function readJsonBody(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > maximumBodyBytes) throw new Error("request_too_large");
    chunks.push(chunk);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new Error("invalid_json");
  }
}

function respond(response, status, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "Cache-Control": "no-store",
    "Content-Length": Buffer.byteLength(body),
    "Content-Type": "application/json; charset=utf-8",
  });
  response.end(body);
}

let pairingInProgress = false;
let t3Process;

const broker = createServer(async (request, response) => {
  if (request.method === "GET" && request.url === "/healthz") {
    try {
      const t3Response = await fetch(`http://127.0.0.1:${t3Port}/`, {
        signal: AbortSignal.timeout(2000),
      });
      respond(response, t3Response.ok ? 200 : 503, {
        status: t3Response.ok ? "ready" : "degraded",
      });
    } catch {
      respond(response, 503, { status: "unavailable" });
    }
    return;
  }
  if (request.method !== "POST" || request.url !== "/pairing") {
    respond(response, 404, { error: "not_found" });
    return;
  }
  if (pairingInProgress) {
    respond(response, 429, { error: "pairing_busy" });
    return;
  }
  pairingInProgress = true;
  try {
    const body = await readJsonBody(request);
    if (
      typeof body.label !== "string"
      || body.label.length < 1
      || body.label.length > 120
      || !/^[A-Za-z0-9_.-]+$/.test(body.label)
    ) {
      respond(response, 400, { error: "invalid_label" });
      return;
    }
    const raw = await runCli([
      "auth",
      "pairing",
      "create",
      "--ttl",
      "15m",
      "--label",
      body.label,
      "--json",
      "--base-dir",
      baseDirectory,
      "--base-url",
      publicUrl,
    ]);
    const result = JSON.parse(raw);
    if (
      typeof result.credential !== "string"
      || result.credential.length < 1
      || result.credential.length > 4096
      || typeof result.expiresAt !== "string"
      || Number.isNaN(Date.parse(result.expiresAt))
    ) {
      throw new Error("invalid_pairing_result");
    }
    respond(response, 201, {
      credential: result.credential,
      expiresAt: result.expiresAt,
      label: typeof result.label === "string" ? result.label : body.label,
    });
  } catch (error) {
    const status = error instanceof Error && error.message === "request_too_large" ? 413 : 503;
    respond(response, status, { error: status === 413 ? "request_too_large" : "pairing_unavailable" });
  } finally {
    pairingInProgress = false;
  }
});

async function start() {
  await runCli([
    "project",
    "add",
    workspaceDirectory,
    "--title",
    "GLIO Proteogen",
    "--base-dir",
    baseDirectory,
  ], { allowExistingProject: true });
  t3Process = spawn(process.execPath, [
    cliPath,
    "--log-level",
    "warn",
    "serve",
    "--mode",
    "web",
    "--host",
    "0.0.0.0",
    "--port",
    String(t3Port),
    "--base-dir",
    baseDirectory,
    "--no-browser",
  ], {
    cwd: workspaceDirectory,
    env: childEnvironment,
    stdio: ["ignore", "ignore", "inherit"],
  });
  t3Process.once("error", () => process.exit(1));
  t3Process.once("close", (code) => process.exit(code ?? 1));
  broker.listen(brokerPort, "0.0.0.0");
}

function shutdown() {
  broker.close();
  t3Process?.kill("SIGTERM");
}

process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);

start().catch(() => process.exit(1));
