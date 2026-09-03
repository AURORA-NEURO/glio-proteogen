import { createHash, randomBytes, randomUUID, scryptSync, timingSafeEqual } from "node:crypto";
import { mkdirSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

export const SESSION_COOKIE = "glio_session";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 14;

export type Account = {
  id: string;
  email: string;
  createdAt: string;
};

type AccountRow = {
  id: string;
  email: string;
  created_at: string;
  password_hash: string;
};

type SessionRow = {
  account_id: string;
  email: string;
  created_at: string;
};

function databasePath() {
  return process.env.GLIO_AUTH_DATABASE_PATH ?? path.join(process.cwd(), ".data", "auth.sqlite3");
}

function openDatabase() {
  const filename = databasePath();
  mkdirSync(path.dirname(filename), { recursive: true });
  const database = new DatabaseSync(filename);
  database.exec("PRAGMA busy_timeout = 5000;");
  database.exec("PRAGMA foreign_keys = ON;");
  database.exec(`
    CREATE TABLE IF NOT EXISTS accounts (
      id TEXT PRIMARY KEY,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions (
      token_hash TEXT PRIMARY KEY,
      account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      created_at TEXT NOT NULL,
      expires_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS sessions_account_idx ON sessions(account_id);
    CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions(expires_at);
  `);
  return database;
}

function normalizeEmail(value: unknown) {
  if (typeof value !== "string") throw new Error("Enter a valid email address.");
  const email = value.trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254) {
    throw new Error("Enter a valid email address.");
  }
  return email;
}

function validatePassword(value: unknown) {
  if (typeof value !== "string" || value.length < 10 || value.length > 256) {
    throw new Error("Use a password between 10 and 256 characters.");
  }
  return value;
}

function hashPassword(password: string) {
  const salt = randomBytes(16).toString("hex");
  const digest = scryptSync(password, salt, 64).toString("hex");
  return `${salt}:${digest}`;
}

function verifyPassword(password: string, stored: string) {
  const [salt, expectedHex] = stored.split(":");
  if (!salt || !expectedHex) return false;
  const expected = Buffer.from(expectedHex, "hex");
  const actual = scryptSync(password, salt, expected.length);
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}

function publicAccount(row: Pick<AccountRow, "id" | "email" | "created_at">): Account {
  return { id: row.id, email: row.email, createdAt: row.created_at };
}

function hashSession(token: string) {
  return createHash("sha256").update(token).digest("hex");
}

export function createAccount(emailInput: unknown, passwordInput: unknown) {
  const email = normalizeEmail(emailInput);
  const password = validatePassword(passwordInput);
  const account: AccountRow = {
    id: randomUUID(),
    email,
    password_hash: hashPassword(password),
    created_at: new Date().toISOString(),
  };
  const database = openDatabase();
  try {
    database
      .prepare("INSERT INTO accounts (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)")
      .run(account.id, account.email, account.password_hash, account.created_at);
    return { account: publicAccount(account), sessionToken: createSession(database, account.id) };
  } finally {
    database.close();
  }
}

export function authenticateAccount(emailInput: unknown, passwordInput: unknown) {
  const email = normalizeEmail(emailInput);
  const password = validatePassword(passwordInput);
  const database = openDatabase();
  try {
    const row = database.prepare("SELECT id, email, password_hash, created_at FROM accounts WHERE email = ?").get(email) as AccountRow | undefined;
    if (!row || !verifyPassword(password, row.password_hash)) throw new Error("Email or password is incorrect.");
    return { account: publicAccount(row), sessionToken: createSession(database, row.id) };
  } finally {
    database.close();
  }
}

function createSession(database: DatabaseSync, accountId: string) {
  const token = randomBytes(32).toString("base64url");
  const now = new Date();
  const expiresAt = new Date(now.getTime() + SESSION_TTL_SECONDS * 1000).toISOString();
  database
    .prepare("INSERT INTO sessions (token_hash, account_id, created_at, expires_at) VALUES (?, ?, ?, ?)")
    .run(hashSession(token), accountId, now.toISOString(), expiresAt);
  return token;
}

export function getAccountForSession(token: string | undefined) {
  if (!token) return null;
  const database = openDatabase();
  try {
    const now = new Date().toISOString();
    database.prepare("DELETE FROM sessions WHERE expires_at <= ?").run(now);
    const row = database
      .prepare(`
        SELECT sessions.account_id, accounts.email, accounts.created_at
        FROM sessions JOIN accounts ON accounts.id = sessions.account_id
        WHERE sessions.token_hash = ? AND sessions.expires_at > ?
      `)
      .get(hashSession(token), now) as SessionRow | undefined;
    return row ? { id: row.account_id, email: row.email, createdAt: row.created_at } : null;
  } finally {
    database.close();
  }
}

export function deleteSession(token: string | undefined) {
  if (!token) return;
  const database = openDatabase();
  try {
    database.prepare("DELETE FROM sessions WHERE token_hash = ?").run(hashSession(token));
  } finally {
    database.close();
  }
}

export function deleteAccount(accountId: string) {
  const database = openDatabase();
  try {
    database.prepare("DELETE FROM accounts WHERE id = ?").run(accountId);
  } finally {
    database.close();
  }
}

export function sessionCookieOptions() {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/api",
    maxAge: SESSION_TTL_SECONDS,
  };
}
