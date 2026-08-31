import { NextResponse } from "next/server";
import { createAccount, deleteAccount, sessionCookieOptions, SESSION_COOKIE } from "@/lib/auth";
import { issuePairingCredential } from "@/lib/pairing";

export const runtime = "nodejs";

export async function POST(request: Request) {
  let body: { email?: unknown; password?: unknown };
  try {
    body = (await request.json()) as { email?: unknown; password?: unknown };
  } catch {
    return NextResponse.json({ error: "Send a JSON email and password." }, { status: 400 });
  }
  let result: ReturnType<typeof createAccount>;
  try {
    result = createAccount(body.email, body.password);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to create the account.";
    const status = message.includes("UNIQUE constraint failed") ? 409 : 400;
    return NextResponse.json({ error: status === 409 ? "An account with that email already exists." : message }, { status });
  }
  let pairing;
  try {
    pairing = await issuePairingCredential(result.account.email);
  } catch {
    deleteAccount(result.account.id);
    return NextResponse.json(
      { error: "T3 Code is unavailable, so the account was not created. Retry when the agent runtime is ready." },
      { status: 503 },
    );
  }
  const response = NextResponse.json(
    {
      account: result.account,
      pairing,
      pairingAvailable: true,
      message: "Account created and GLIO Agent Console paired.",
    },
    { status: 201 },
  );
  response.cookies.set(SESSION_COOKIE, result.sessionToken, sessionCookieOptions());
  return response;
}
