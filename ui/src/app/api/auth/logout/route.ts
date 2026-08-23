import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { deleteSession, SESSION_COOKIE } from "@/lib/auth";

export const runtime = "nodejs";

export async function POST() {
  const cookieStore = await cookies();
  deleteSession(cookieStore.get(SESSION_COOKIE)?.value);
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production", path: "/", maxAge: 0 });
  return response;
}
