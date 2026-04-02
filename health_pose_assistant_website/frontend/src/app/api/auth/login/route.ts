import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

function shouldUseSecureCookie(req: NextRequest) {
  const configured = process.env.AUTH_COOKIE_SECURE;
  if (configured === "true") {
    return true;
  }
  if (configured === "false") {
    return false;
  }

  const forwardedProto = req.headers.get("x-forwarded-proto");
  const requestProto = forwardedProto?.split(",")[0].trim() || req.nextUrl.protocol.replace(":", "");

  return process.env.NODE_ENV === "production" && requestProto === "https";
}

export async function POST(req: NextRequest) {
  const body = await req.json();

  const res = await fetch(`${BACKEND_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const error = await res.json();
    return NextResponse.json(error, { status: res.status });
  }

  const data = await res.json();

  const cookieStore = await cookies();
  cookieStore.set("access_token", data.access_token, {
    httpOnly: true,
    secure: shouldUseSecureCookie(req),
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60, // 1 hour, matches JWT expiry
  });

  return NextResponse.json({ success: true });
}
