import { expect, test, type Page, type Route } from "@playwright/test";

test.describe.configure({ mode: "serial" });

function identity(testIndex: number) {
  return `e2e-${process.pid}-${testIndex}@example.invalid`;
}

function passphrase() {
  return ["bounded", "browser", "passphrase"].join("-");
}

async function mockEmptyApiConsole(page: Page, seenCookies: Array<string | undefined>) {
  await page.route("**/backend/**", async (route: Route) => {
    seenCookies.push(route.request().headers().cookie);
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith("/livez")) {
      await route.fulfill({ json: { status: "ok" } });
    } else if (pathname.endsWith("/readyz")) {
      await route.fulfill({ status: 503, json: { status: "degraded" } });
    } else if (pathname.endsWith("/v2/deployment/catalog")) {
      await route.fulfill({ json: {
        catalog_digest: `sha256:${"a".repeat(64)}`,
        catalog_version: 2,
        environment: "e2e",
        operation_count: 0,
        operations: [],
        version: "1.0.0",
      } });
    } else if (pathname.endsWith("/openapi.json")) {
      await route.fulfill({ json: { openapi: "3.1.0", paths: {} } });
    } else {
      await route.fulfill({ status: 404, json: { detail: "not found" } });
    }
  });
}

test("registers, pairs, refreshes pairing, signs out, and signs back in", async ({ page }, testInfo) => {
  const email = identity(testInfo.parallelIndex);
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(passphrase());
  const [registration] = await Promise.all([
    page.waitForResponse("**/api/auth/register"),
    page.getByRole("button", { name: "Create account" }).click(),
  ]);

  expect(registration.status()).toBe(201);
  expect(await registration.headerValue("set-cookie")).toMatch(/glio_session=.*Path=\/api;.*HttpOnly;.*SameSite=lax/i);
  await expect(page.getByText("Account active")).toBeVisible();
  await expect(page.getByText(email)).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem("glio_pending_pairing"))).toBeNull();

  await page.getByRole("link", { name: /Open GLIO Agent Console/ }).click();
  await expect(page).toHaveURL(/\/console$/);
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  await expect(page.locator("iframe[title='GLIO Proteogen Agent Console']")).toHaveAttribute(
    "src",
    /^http:\/\/127\.0\.0\.1:3775\/pair#token=/,
  );

  const pairing = await page.request.post("/api/pairing/token");
  expect(pairing.status()).toBe(200);
  expect((await pairing.json()).pairing.pairingUrl).toMatch(/^http:\/\/127\.0\.0\.1:3775\/pair#token=/);

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/register$/);
  expect((await page.request.get("/api/auth/me")).status()).toBe(401);
  expect((await page.request.post("/api/pairing/token")).status()).toBe(401);

  await page.getByRole("button", { name: "Already have an account? Sign in" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(`${passphrase()}-wrong`);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Email or password is incorrect.")).toBeVisible();
  await page.getByLabel("Password").fill(passphrase());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Account active")).toBeVisible();
});

test("shows authenticated API-console navigation and never forwards its session cookie", async ({ page }, testInfo) => {
  const email = identity(testInfo.parallelIndex + 100);
  const registration = await page.request.post("/api/auth/register", {
    data: { email, password: passphrase() },
  });
  expect(registration.status()).toBe(201);

  const seenCookies: Array<string | undefined> = [];
  await mockEmptyApiConsole(page, seenCookies);
  await page.goto("/api-console");
  await expect(page.getByRole("link", { name: "Agent console ↗", exact: true })).toBeVisible();
  await expect(page.getByText("Ready degraded", { exact: true })).toBeVisible();
  await expect(page.getByText("Live online", { exact: true })).toBeVisible();
  await expect.poll(() => seenCookies.length).toBeGreaterThanOrEqual(4);
  expect(seenCookies).toEqual(expect.arrayContaining([undefined]));
  expect(seenCookies.filter(Boolean)).toEqual([]);
});

test("recovers cleanly when an authenticated console pairing attempt is degraded", async ({ page }, testInfo) => {
  const email = identity(testInfo.parallelIndex + 200);
  expect((await page.request.post("/api/auth/register", {
    data: { email, password: passphrase() },
  })).status()).toBe(201);
  expect((await page.request.post("http://127.0.0.1:3775/control/fail-next")).status()).toBe(200);

  await page.goto("/console");
  await expect(page.getByText("Offline", { exact: true })).toBeVisible();
  await expect(page.getByText(/T3 Code is not available/)).toBeVisible();
  await page.getByRole("button", { name: "Retry pairing" }).click();
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
});

test("rolls registration back when T3 pairing is unavailable", async ({ page }, testInfo) => {
  const email = identity(testInfo.parallelIndex + 300);
  expect((await page.request.post("http://127.0.0.1:3775/control/fail-next")).status()).toBe(200);

  const failed = await page.request.post("/api/auth/register", {
    data: { email, password: passphrase() },
  });
  expect(failed.status()).toBe(503);
  await expect(failed.json()).resolves.toEqual({
    error: "T3 Code is unavailable, so the account was not created. Retry when the agent runtime is ready.",
  });
  expect((await page.request.get("/api/auth/me")).status()).toBe(401);

  const retried = await page.request.post("/api/auth/register", {
    data: { email, password: passphrase() },
  });
  expect(retried.status()).toBe(201);
  expect((await retried.json()).pairingAvailable).toBe(true);
});
