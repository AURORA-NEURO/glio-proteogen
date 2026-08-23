import { NextResponse } from "next/server";
import { createAccount, sessionCookieOptions, SESSION_COOKIE } from "@/lib/auth";
import { issuePairingCredential } from "@/lib/pairing";

export const runtime = "nodejs";

export async function POST(request: Request) {
  let body: { email?: unknown; password?: unknown };
  try {
    body = (await request.json()) as { email?: unknown; password?: unknown };
  } catch {
    return NextResponse.json({ error: "Send a JSON email and password." }, { status: 400 });
  }
  try {
    const result = createAccount(body.email, body.password);
    let pairing = null;
    try {
      pairing = await issuePairingCredential(result.account.email);
    } catch {
      pairing = null;
    }
    const response = NextResponse.json(
      {
        account: result.account,
        pairing,
        pairingAvailable: pairing !== null,
        message: pairing ? "Account created and GLIO Agent Console paired." : "Account created. Start T3 Code, then pair from your account.",
      },
      { status: 201 },
    );
    response.cookies.set(SESSION_COOKIE, result.sessionToken, sessionCookieOptions());
    return response;
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to create the account.";
    const status = message.includes("UNIQUE constraint failed") ? 409 : 400;
    return NextResponse.json({ error: status === 409 ? "An account with that email already exists." : message }, { status });
  }
}
