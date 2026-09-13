import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const doubles = vi.hoisted(() => ({
  authenticateAccount: vi.fn(),
  cookies: vi.fn(),
  createAccount: vi.fn(),
  deleteAccount: vi.fn(),
  deleteSession: vi.fn(),
  getAccountForSession: vi.fn(),
  issuePairingCredential: vi.fn(),
  sessionCookieOptions: vi.fn(() => ({
    httpOnly: true,
    maxAge: 1_209_600,
    path: "/api",
    sameSite: "lax" as const,
    secure: false,
  })),
}));

vi.mock("@/lib/auth", () => ({
  SESSION_COOKIE: "glio_session",
  authenticateAccount: doubles.authenticateAccount,
  createAccount: doubles.createAccount,
  deleteAccount: doubles.deleteAccount,
  deleteSession: doubles.deleteSession,
  getAccountForSession: doubles.getAccountForSession,
  sessionCookieOptions: doubles.sessionCookieOptions,
}));
vi.mock("@/lib/pairing", () => ({
  issuePairingCredential: doubles.issuePairingCredential,
}));
vi.mock("next/headers", () => ({ cookies: doubles.cookies }));

import { POST as login } from "../../src/app/api/auth/login/route";
import { POST as logout } from "../../src/app/api/auth/logout/route";
import { GET as me } from "../../src/app/api/auth/me/route";
import { POST as register } from "../../src/app/api/auth/register/route";
import { GET as health } from "../../src/app/healthz/route";
import { POST as pair } from "../../src/app/api/pairing/token/route";

const account = {
  id: "account-1",
  email: "researcher@example.org",
  createdAt: "2030-01-01T00:00:00.000Z",
};
const pairing = {
  credential: "opaque-pairing-credential",
  expiresAt: "2030-01-01T00:15:00.000Z",
  label: "GLIO-Proteogen-researcher-example.org",
  pairingUrl: "http://127.0.0.1:3773/pair#token=opaque-pairing-credential",
  serverUrl: "http://127.0.0.1:3773",
};

function jsonRequest(path: string, body: unknown) {
  return new Request(`http://ui.test${path}`, {
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
    method: "POST",
  });
}

function malformedRequest(path: string) {
  return new Request(`http://ui.test${path}`, {
    body: "{",
    headers: { "Content-Type": "application/json" },
    method: "POST",
  });
}

function requestPassphrase() {
  return ["bounded", "route", "passphrase"].join("-");
}

function cookieStore(value?: string) {
  return { get: vi.fn(() => value === undefined ? undefined : { value }) };
}

beforeEach(() => {
  vi.clearAllMocks();
  doubles.cookies.mockResolvedValue(cookieStore("session-value"));
  doubles.createAccount.mockReturnValue({ account, sessionToken: "session-value" });
  doubles.authenticateAccount.mockReturnValue({ account, sessionToken: "session-value" });
  doubles.getAccountForSession.mockReturnValue(account);
  doubles.issuePairingCredential.mockResolvedValue(pairing);
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("account API routes", () => {
  it("registers only after pairing succeeds and emits an API-scoped session", async () => {
    const response = await register(jsonRequest("/api/auth/register", {
      email: account.email,
      password: requestPassphrase(),
    }));

    expect(response.status).toBe(201);
    await expect(response.json()).resolves.toEqual({
      account,
      message: "Account created and GLIO Agent Console paired.",
      pairing,
      pairingAvailable: true,
    });
    expect(response.headers.get("set-cookie")).toContain("Path=/api");
    expect(doubles.deleteAccount).not.toHaveBeenCalled();
  });

  it("rejects malformed, duplicate, invalid, and opaque registration failures", async () => {
    expect((await register(malformedRequest("/api/auth/register"))).status).toBe(400);

    doubles.createAccount.mockImplementationOnce(() => {
      throw new Error("UNIQUE constraint failed: accounts.email");
    });
    let response = await register(jsonRequest("/api/auth/register", {}));
    expect(response.status).toBe(409);
    await expect(response.json()).resolves.toEqual({ error: "An account with that email already exists." });

    doubles.createAccount.mockImplementationOnce(() => {
      throw new Error("Enter a valid email address.");
    });
    response = await register(jsonRequest("/api/auth/register", {}));
    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({ error: "Enter a valid email address." });

    doubles.createAccount.mockImplementationOnce(() => { throw "private detail"; });
    response = await register(jsonRequest("/api/auth/register", {}));
    await expect(response.json()).resolves.toEqual({ error: "Unable to create the account." });
  });

  it("rolls back a newly created account when pairing is unavailable", async () => {
    doubles.issuePairingCredential.mockRejectedValueOnce(new Error("private runtime detail"));
    const response = await register(jsonRequest("/api/auth/register", {
      email: account.email,
      password: requestPassphrase(),
    }));

    expect(response.status).toBe(503);
    expect(doubles.deleteAccount).toHaveBeenCalledWith(account.id);
    expect(response.headers.get("set-cookie")).toBeNull();
    await expect(response.json()).resolves.toEqual({
      error: "T3 Code is unavailable, so the account was not created. Retry when the agent runtime is ready.",
    });
  });

  it("authenticates valid logins and sanitizes all failures", async () => {
    expect((await login(malformedRequest("/api/auth/login"))).status).toBe(400);

    let response = await login(jsonRequest("/api/auth/login", {
      email: account.email,
      password: requestPassphrase(),
    }));
    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toContain("Path=/api");
    await expect(response.json()).resolves.toEqual({ account });

    doubles.authenticateAccount.mockImplementationOnce(() => {
      throw new Error("Email or password is incorrect.");
    });
    response = await login(jsonRequest("/api/auth/login", {}));
    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({ error: "Email or password is incorrect." });

    doubles.authenticateAccount.mockImplementationOnce(() => { throw null; });
    response = await login(jsonRequest("/api/auth/login", {}));
    await expect(response.json()).resolves.toEqual({ error: "Unable to sign in." });
  });

  it("reads, revokes, and clears sessions with the same cookie scope", async () => {
    let response = await me();
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ account });
    expect(doubles.getAccountForSession).toHaveBeenCalledWith("session-value");

    doubles.getAccountForSession.mockReturnValueOnce(null);
    response = await me();
    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({ account: null });

    vi.stubEnv("NODE_ENV", "production");
    response = await logout();
    expect(doubles.deleteSession).toHaveBeenCalledWith("session-value");
    const clearedCookie = response.headers.get("set-cookie") ?? "";
    expect(clearedCookie).toContain("Path=/api");
    expect(clearedCookie).toContain("Max-Age=0");
    expect(clearedCookie).toContain("HttpOnly");
    expect(clearedCookie).toContain("Secure");
    expect(clearedCookie).toContain("SameSite=lax");

    doubles.cookies.mockResolvedValueOnce(cookieStore());
    await logout();
    expect(doubles.deleteSession).toHaveBeenLastCalledWith(undefined);
  });
});

describe("pairing and UI health routes", () => {
  it("requires a valid session before issuing a fresh pairing credential", async () => {
    let response = await pair();
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ pairing });
    expect(doubles.issuePairingCredential).toHaveBeenCalledWith(account.email);

    doubles.getAccountForSession.mockReturnValueOnce(null);
    response = await pair();
    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({
      error: "Sign in before pairing the GLIO Agent Console.",
    });
  });

  it("maps all pairing broker failures to a sanitized degraded response", async () => {
    doubles.issuePairingCredential.mockRejectedValueOnce(new Error("private broker detail"));
    const response = await pair();
    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      error: "T3 Code is not available. Start the GLIO Agent Console server and retry.",
    });
  });

  it("reports uncached UI liveness independently of the backend", async () => {
    const response = health();
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    await expect(response.json()).resolves.toEqual({
      service: "glio-proteogen-ui",
      status: "ok",
    });
  });
});
