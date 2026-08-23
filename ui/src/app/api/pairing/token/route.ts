import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { getAccountForSession, SESSION_COOKIE } from "@/lib/auth";
import { issuePairingCredential } from "@/lib/pairing";

export const runtime = "nodejs";

export async function POST() {
  const account = getAccountForSession((await cookies()).get(SESSION_COOKIE)?.value);
  if (!account) return NextResponse.json({ error: "Sign in before pairing the GLIO Agent Console." }, { status: 401 });
  try {
    return NextResponse.json({ pairing: await issuePairingCredential(account.email) });
  } catch {
    return NextResponse.json({ error: "T3 Code is not available. Start the GLIO Agent Console server and retry." }, { status: 503 });
  }
}
