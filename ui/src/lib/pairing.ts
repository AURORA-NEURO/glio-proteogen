import { spawn } from "node:child_process";
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

function t3BaseDir() {
  return process.env.T3_CODE_BASE_DIR ?? process.env.T3CODE_HOME ?? path.join(homedir(), ".t3");
}

function t3ServerUrl() {
  return (process.env.T3_CODE_URL ?? "http://127.0.0.1:3773").replace(/\/$/, "");
}

function cliCommand() {
  return process.env.T3_CODE_CLI ?? (process.platform === "win32" ? "npx.cmd" : "npx");
}

function runT3Pairing(label: string) {
  return new Promise<string>((resolve, reject) => {
    const child = spawn(
      cliCommand(),
      ["--yes", "t3@latest", "auth", "pairing", "create", "--ttl", "15m", "--label", label, "--json"],
      { cwd: process.cwd(), env: { ...process.env, T3CODE_HOME: t3BaseDir() }, windowsHide: true, shell: process.platform === "win32" },
    );
    let stdout = "";
    let finished = false;
    const timer = setTimeout(() => {
      if (finished) return;
      finished = true;
      child.kill();
      reject(new Error("T3 Code pairing timed out."));
    }, 30_000);
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
      if (stdout.length > 100_000) {
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

export async function issuePairingCredential(accountLabel: string): Promise<PairingCredential> {
  const label = `GLIO-Proteogen-${accountLabel.replace(/[^a-z0-9_.-]+/gi, "-")}`.slice(0, 120);
  const raw = await runT3Pairing(label);
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
