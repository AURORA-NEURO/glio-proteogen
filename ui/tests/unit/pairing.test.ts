import { EventEmitter } from "node:events";

import { afterEach, describe, expect, it, vi } from "vitest";

import { issuePairingCredential } from "../../src/lib/pairing";

type FakeChild = EventEmitter & {
  stdout: EventEmitter;
  kill: ReturnType<typeof vi.fn>;
};

const originalEnvironment = {
  T3_CODE_BASE_DIR: process.env.T3_CODE_BASE_DIR,
  T3_CODE_CLI: process.env.T3_CODE_CLI,
  T3_CODE_URL: process.env.T3_CODE_URL,
  T3_PAIRING_BROKER_URL: process.env.T3_PAIRING_BROKER_URL,
  T3CODE_HOME: process.env.T3CODE_HOME,
};

function restoreEnvironment() {
  for (const [name, value] of Object.entries(originalEnvironment)) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
}

function installFakePairingProcess() {
  const child = Object.assign(new EventEmitter(), {
    stdout: new EventEmitter(),
    kill: vi.fn(),
  }) as FakeChild;
  const spawn = vi.fn(() => child);
  vi.spyOn(process, "getBuiltinModule").mockReturnValue({ spawn } as never);
  return { child, spawn };
}

afterEach(() => {
  restoreEnvironment();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("T3 Code pairing", () => {
  it("issues a sanitized credential through the configured CLI and runtime", async () => {
    process.env.T3_CODE_CLI = "t3-test-cli";
    process.env.T3_CODE_BASE_DIR = "/tmp/glio-t3";
    process.env.T3_CODE_URL = "https://console.example.test/";
    const { child, spawn } = installFakePairingProcess();

    const pending = issuePairingCredential("Researcher + Lab@example.org");
    child.stdout.emit("data", Buffer.from(JSON.stringify({
      credential: "credential value",
      expiresAt: "2030-01-01T00:15:00.000Z",
    })));
    child.emit("close", 0);

    await expect(pending).resolves.toEqual({
      credential: "credential value",
      expiresAt: "2030-01-01T00:15:00.000Z",
      label: "GLIO-Proteogen-Researcher-Lab-example.org",
      serverUrl: "https://console.example.test",
      pairingUrl: "https://console.example.test/pair#token=credential%20value",
    });
    expect(spawn).toHaveBeenCalledWith(
      "t3-test-cli",
      [
        "--yes",
        "t3@0.0.35",
        "auth",
        "pairing",
        "create",
        "--ttl",
        "15m",
        "--label",
        "GLIO-Proteogen-Researcher-Lab-example.org",
        "--json",
        "--base-dir",
        "/tmp/glio-t3",
        "--base-url",
        "https://console.example.test",
      ],
      expect.objectContaining({
        cwd: process.cwd(),
        env: expect.objectContaining({ T3CODE_HOME: "/tmp/glio-t3" }),
        windowsHide: true,
      }),
    );
  });

  it("uses T3CODE_HOME and preserves a valid CLI label", async () => {
    delete process.env.T3_CODE_BASE_DIR;
    process.env.T3CODE_HOME = "/tmp/t3code-home";
    process.env.T3_CODE_CLI = "t3-test-cli";
    const { child, spawn } = installFakePairingProcess();

    const pending = issuePairingCredential("x".repeat(160));
    child.stdout.emit("data", Buffer.from(JSON.stringify({
      credential: "credential",
      expiresAt: "2030-01-01T00:15:00.000Z",
      label: "issuer-label",
    })));
    child.emit("close", 0);

    await expect(pending).resolves.toMatchObject({ label: "issuer-label" });
    const args = spawn.mock.calls[0]?.[1] as string[];
    expect(args[args.indexOf("--label") + 1]).toHaveLength(120);
    expect(spawn.mock.calls[0]?.[2]).toEqual(expect.objectContaining({
      env: expect.objectContaining({ T3CODE_HOME: "/tmp/t3code-home" }),
    }));
  });

  it("sanitizes malformed and incomplete successful CLI responses", async () => {
    process.env.T3_CODE_CLI = "t3-test-cli";
    let processDouble = installFakePairingProcess();
    let pending = issuePairingCredential("researcher@example.org");
    processDouble.child.stdout.emit("data", Buffer.from("not-json"));
    processDouble.child.emit("close", 0);
    await expect(pending).rejects.toThrow("returned an invalid response");

    vi.restoreAllMocks();
    processDouble = installFakePairingProcess();
    pending = issuePairingCredential("researcher@example.org");
    processDouble.child.stdout.emit("data", Buffer.from(JSON.stringify({ credential: 7 })));
    processDouble.child.emit("close", 0);
    await expect(pending).rejects.toThrow("returned an incomplete response");
  });

  it("maps spawn and nonzero-exit failures to a stable unavailable error", async () => {
    process.env.T3_CODE_CLI = "t3-test-cli";
    let processDouble = installFakePairingProcess();
    let pending = issuePairingCredential("researcher@example.org");
    processDouble.child.emit("error", new Error("sensitive spawn detail"));
    await expect(pending).rejects.toThrow("pairing service is unavailable");
    processDouble.child.emit("close", 2);

    vi.restoreAllMocks();
    processDouble = installFakePairingProcess();
    pending = issuePairingCredential("researcher@example.org");
    processDouble.child.emit("close", 2);
    await expect(pending).rejects.toThrow("pairing service is unavailable");
    processDouble.child.emit("error", new Error("late detail"));
  });

  it("uses pinned platform defaults when no CLI override is configured", async () => {
    delete process.env.T3_CODE_CLI;
    delete process.env.T3_CODE_BASE_DIR;
    delete process.env.T3CODE_HOME;
    delete process.env.T3_CODE_URL;
    const platform = vi.spyOn(process, "platform", "get").mockReturnValue("linux");
    let processDouble = installFakePairingProcess();
    let pending = issuePairingCredential("default@example.org");
    processDouble.child.stdout.emit("data", Buffer.from(JSON.stringify({
      credential: "credential",
      expiresAt: "2030-01-01T00:15:00.000Z",
    })));
    processDouble.child.emit("close", 0);
    await expect(pending).resolves.toMatchObject({ serverUrl: "http://127.0.0.1:3773" });
    expect(processDouble.spawn.mock.calls[0]?.[0]).toBe("npx");

    vi.restoreAllMocks();
    platform.mockRestore();
    vi.spyOn(process, "platform", "get").mockReturnValue("win32");
    processDouble = installFakePairingProcess();
    pending = issuePairingCredential("default@example.org");
    processDouble.child.stdout.emit("data", Buffer.from(JSON.stringify({
      credential: "credential",
      expiresAt: "2030-01-01T00:15:00.000Z",
    })));
    processDouble.child.emit("close", 0);
    await expect(pending).resolves.toBeDefined();
    expect(processDouble.spawn.mock.calls[0]?.[0]).toBe("npx.cmd");
  });

  it("bounds CLI output before parsing", async () => {
    process.env.T3_CODE_CLI = "t3-test-cli";
    const { child } = installFakePairingProcess();
    const pending = issuePairingCredential("researcher@example.org");
    child.stdout.emit("data", Buffer.alloc(100_001, 65));

    await expect(pending).rejects.toThrow("returned an invalid response");
    expect(child.kill).toHaveBeenCalledOnce();
  });

  it("kills a pairing subprocess that exceeds the bounded timeout", async () => {
    vi.useFakeTimers();
    process.env.T3_CODE_CLI = "t3-test-cli";
    const { child } = installFakePairingProcess();
    const pending = issuePairingCredential("researcher@example.org");
    const rejection = expect(pending).rejects.toThrow("pairing timed out");

    await vi.advanceTimersByTimeAsync(30_000);

    await rejection;
    expect(child.kill).toHaveBeenCalledOnce();
  });

  it("uses the bounded internal broker without spawning a package runner", async () => {
    process.env.T3_PAIRING_BROKER_URL = "http://t3-code:3774/pairing";
    process.env.T3_CODE_URL = "https://console.example.test";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      credential: "broker-credential",
      expiresAt: "2030-01-01T00:15:00.000Z",
      label: "broker-label",
    }), { status: 201 }));
    const processModule = vi.spyOn(process, "getBuiltinModule");

    await expect(issuePairingCredential("Researcher@example.org")).resolves.toMatchObject({
      credential: "broker-credential",
      label: "broker-label",
      pairingUrl: "https://console.example.test/pair#token=broker-credential",
    });
    expect(fetchMock).toHaveBeenCalledWith("http://t3-code:3774/pairing", expect.objectContaining({
      body: JSON.stringify({ label: "GLIO-Proteogen-Researcher-example.org" }),
      cache: "no-store",
      method: "POST",
    }));
    expect(processModule).not.toHaveBeenCalled();
  });

  it("sanitizes broker transport, status, body, and response-bound failures", async () => {
    process.env.T3_PAIRING_BROKER_URL = "http://t3-code:3774/pairing";
    const fetchMock = vi.spyOn(globalThis, "fetch");

    fetchMock.mockRejectedValueOnce(new Error("private network detail"));
    await expect(issuePairingCredential("researcher@example.org")).rejects.toThrow("pairing service is unavailable");

    fetchMock.mockResolvedValueOnce(new Response("unavailable", { status: 503 }));
    await expect(issuePairingCredential("researcher@example.org")).rejects.toThrow("pairing service is unavailable");

    fetchMock.mockResolvedValueOnce({
      ok: true,
      text: vi.fn().mockRejectedValue(new Error("private stream detail")),
    } as unknown as Response);
    await expect(issuePairingCredential("researcher@example.org")).rejects.toThrow("pairing service is unavailable");

    fetchMock.mockResolvedValueOnce(new Response("x".repeat(100_001)));
    await expect(issuePairingCredential("researcher@example.org")).rejects.toThrow("returned an invalid response");
  });
});
