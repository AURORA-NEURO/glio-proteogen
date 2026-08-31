import { homedir } from "node:os";
import path from "node:path";

export type PairingCredential = {
  credential: string;
  expiresAt: string;
  label: string;
  serverUrl: string;
  pairingUrl: string;
};

type T3PairingResult = {
  credential?: unknown;
  expiresAt?: unknown;
  label?: unknown;
};

const T3_PACKAGE = "t3@0.0.35";
const PAIRING_TIMEOUT_MS = 30_000;
const MAX_PAIRING_RESPONSE_BYTES = 100_000;

function t3BaseDir() {
  return process.env.T3_CODE_BASE_DIR ?? process.env.T3CODE_HOME ?? path.join(homedir(), ".t3");
}

function t3ServerUrl() {
  return (process.env.T3_CODE_URL ?? "http://127.0.0.1:3773").replace(/\/$/, "");
}

function cliCommand() {
  return process.env.T3_CODE_CLI ?? (process.platform === "win32" ? "npx.cmd" : "npx");
}

async function runT3Pairing(label: string) {
  const childProcess = process.getBuiltinModule("node:child_process") as typeof import("node:child_process");
  return new Promise<string>((resolve, reject) => {
    const child = childProcess.spawn(
      cliCommand(),
      [
        "--yes",
        T3_PACKAGE,
        "auth",
        "pairing",
        "create",
        "--ttl",
        "15m",
        "--label",
        label,
        "--json",
        "--base-dir",
        t3BaseDir(),
        "--base-url",
        t3ServerUrl(),
      ],
      { cwd: process.cwd(), env: { ...process.env, T3CODE_HOME: t3BaseDir() }, windowsHide: true, shell: process.platform === "win32" },
    );
    let stdout = "";
    let finished = false;
    const timer = setTimeout(() => {
      if (finished) return;
      finished = true;
      child.kill();
      reject(new Error("T3 Code pairing timed out."));
    }, PAIRING_TIMEOUT_MS);
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
      if (Buffer.byteLength(stdout, "utf8") > MAX_PAIRING_RESPONSE_BYTES) {
        finished = true;
        clearTimeout(timer);
        child.kill();
        reject(new Error("T3 Code pairing returned an invalid response."));
      }
    });
    child.on("error", () => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      reject(new Error("The T3 Code pairing service is unavailable."));
    });
    child.on("close", (code) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error("The T3 Code pairing service is unavailable."));
        return;
      }
      resolve(stdout);
    });
  });
}

async function requestPairingFromBroker(label: string, brokerUrl: string) {
  let response: Response;
  try {
    response = await fetch(brokerUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label }),
      cache: "no-store",
      signal: AbortSignal.timeout(PAIRING_TIMEOUT_MS),
    });
  } catch {
    throw new Error("The T3 Code pairing service is unavailable.");
  }
  let raw: string;
  try {
    raw = await response.text();
  } catch {
    throw new Error("The T3 Code pairing service is unavailable.");
  }
  if (!response.ok) throw new Error("The T3 Code pairing service is unavailable.");
  if (Buffer.byteLength(raw, "utf8") > MAX_PAIRING_RESPONSE_BYTES) {
    throw new Error("The T3 Code pairing service returned an invalid response.");
  }
  return raw;
}

export async function issuePairingCredential(accountLabel: string): Promise<PairingCredential> {
  const label = `GLIO-Proteogen-${accountLabel.replace(/[^a-z0-9_.-]+/gi, "-")}`.slice(0, 120);
  const brokerUrl = process.env.T3_PAIRING_BROKER_URL;
  const raw = brokerUrl
    ? await requestPairingFromBroker(label, brokerUrl)
    : await runT3Pairing(label);
  let result: T3PairingResult;
  try {
    result = JSON.parse(raw) as T3PairingResult;
  } catch {
    throw new Error("The T3 Code pairing service returned an invalid response.");
  }
  if (typeof result.credential !== "string" || typeof result.expiresAt !== "string") {
    throw new Error("The T3 Code pairing service returned an incomplete response.");
  }
  const serverUrl = t3ServerUrl();
  return {
    credential: result.credential,
    expiresAt: result.expiresAt,
    label: typeof result.label === "string" ? result.label : label,
    serverUrl,
    pairingUrl: `${serverUrl}/pair#token=${encodeURIComponent(result.credential)}`,
  };
}
