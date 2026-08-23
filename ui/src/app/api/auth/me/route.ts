import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { getAccountForSession, SESSION_COOKIE } from "@/lib/auth";

export const runtime = "nodejs";

export async function GET() {
  const account = getAccountForSession((await cookies()).get(SESSION_COOKIE)?.value);
  return account ? NextResponse.json({ account }) : NextResponse.json({ account: null }, { status: 401 });
}
