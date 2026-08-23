import { NextResponse } from "next/server";
import { authenticateAccount, sessionCookieOptions, SESSION_COOKIE } from "@/lib/auth";

export const runtime = "nodejs";

export async function POST(request: Request) {
  let body: { email?: unknown; password?: unknown };
  try {
    body = (await request.json()) as { email?: unknown; password?: unknown };
  } catch {
    return NextResponse.json({ error: "Send a JSON email and password." }, { status: 400 });
  }
  try {
    const result = authenticateAccount(body.email, body.password);
    const response = NextResponse.json({ account: result.account });
    response.cookies.set(SESSION_COOKIE, result.sessionToken, sessionCookieOptions());
    return response;
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Unable to sign in." }, { status: 401 });
  }
}
