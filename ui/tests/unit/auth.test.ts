import { DatabaseSync } from "node:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  authenticateAccount,
  createAccount,
  deleteAccount,
  deleteSession,
  getAccountForSession,
  sessionCookieOptions,
} from "../../src/lib/auth";

function fixturePassphrase() {
  return ["bounded", "evidence", "passphrase"].join("-");
}

let temporaryDirectory = "";
let databasePath = "";
let originalDatabasePath: string | undefined;

beforeEach(() => {
  originalDatabasePath = process.env.GLIO_AUTH_DATABASE_PATH;
  temporaryDirectory = mkdtempSync(path.join(tmpdir(), "glio-auth-unit-"));
  databasePath = path.join(temporaryDirectory, "auth.sqlite3");
  process.env.GLIO_AUTH_DATABASE_PATH = databasePath;
});

afterEach(() => {
  if (originalDatabasePath === undefined) delete process.env.GLIO_AUTH_DATABASE_PATH;
  else process.env.GLIO_AUTH_DATABASE_PATH = originalDatabasePath;
  rmSync(temporaryDirectory, { force: true, recursive: true });
});

describe("local account and session storage", () => {
  it("normalizes accounts, authenticates credentials, and revokes only the selected session", () => {
    const passphrase = fixturePassphrase();
    const created = createAccount("  Researcher@Example.ORG ", passphrase);
    expect(created.account.email).toBe("researcher@example.org");
    expect(created.sessionToken).not.toContain(passphrase);
    expect(getAccountForSession(created.sessionToken)).toEqual(created.account);

    const authenticated = authenticateAccount("RESEARCHER@example.org", passphrase);
    expect(authenticated.account).toEqual(created.account);
    expect(authenticated.sessionToken).not.toBe(created.sessionToken);

    deleteSession(created.sessionToken);
    expect(getAccountForSession(created.sessionToken)).toBeNull();
    expect(getAccountForSession(authenticated.sessionToken)).toEqual(created.account);
    expect(() => deleteSession(undefined)).not.toThrow();
    expect(getAccountForSession(undefined)).toBeNull();

    deleteAccount(created.account.id);
    expect(getAccountForSession(authenticated.sessionToken)).toBeNull();
  });

  it("rejects malformed identities, weak credentials, duplicates, and invalid logins", () => {
    const passphrase = fixturePassphrase();
    expect(() => createAccount(7, passphrase)).toThrow("Enter a valid email address.");
    expect(() => createAccount("not-an-email", passphrase)).toThrow(
      "Enter a valid email address.",
    );
    expect(() => createAccount(`${"x".repeat(250)}@example.org`, passphrase)).toThrow(
      "Enter a valid email address.",
    );
    expect(() => createAccount("a@example.org", null)).toThrow(
      "Use a password between 10 and 256 characters.",
    );
    expect(() => createAccount("a@example.org", "short")).toThrow(
      "Use a password between 10 and 256 characters.",
    );
    expect(() => createAccount("a@example.org", "x".repeat(257))).toThrow(
      "Use a password between 10 and 256 characters.",
    );

    createAccount("unique@example.org", passphrase);
    expect(() => createAccount("unique@example.org", passphrase)).toThrow(
      /UNIQUE constraint failed/,
    );
    expect(() => authenticateAccount("missing@example.org", passphrase)).toThrow(
      "Email or password is incorrect.",
    );
    expect(() => authenticateAccount("unique@example.org", `${passphrase}-wrong`)).toThrow(
      "Email or password is incorrect.",
    );
  });

  it("purges expired sessions and safely rejects a malformed stored password hash", () => {
    const passphrase = fixturePassphrase();
    const created = createAccount("expiry@example.org", passphrase);
    const database = new DatabaseSync(databasePath);
    try {
      database.prepare("UPDATE sessions SET expires_at = ?").run("2000-01-01T00:00:00.000Z");
    } finally {
      database.close();
    }
    expect(getAccountForSession(created.sessionToken)).toBeNull();

    const corrupt = new DatabaseSync(databasePath);
    try {
      corrupt.prepare("UPDATE accounts SET password_hash = ?").run("not-a-password-hash");
    } finally {
      corrupt.close();
    }
    expect(() => authenticateAccount("expiry@example.org", passphrase)).toThrow(
      "Email or password is incorrect.",
    );
  });

  it("emits hardened cookies and enables secure transport only in production", () => {
    const originalNodeEnv = process.env.NODE_ENV;
    try {
      process.env.NODE_ENV = "test";
      expect(sessionCookieOptions()).toEqual({
        httpOnly: true,
        sameSite: "lax",
        secure: false,
        path: "/api",
        maxAge: 1_209_600,
      });
      process.env.NODE_ENV = "production";
      expect(sessionCookieOptions().secure).toBe(true);
    } finally {
      if (originalNodeEnv === undefined) delete process.env.NODE_ENV;
      else process.env.NODE_ENV = originalNodeEnv;
    }
  });
});
