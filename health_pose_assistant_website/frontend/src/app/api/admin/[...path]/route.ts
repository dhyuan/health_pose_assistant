import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

async function proxy(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;

  const backendPath = `/api/v1/admin/${path.join("/")}`;
  const url = new URL(backendPath, BACKEND_URL);
  // Forward query parameters
  const searchParams = req.nextUrl.searchParams;
  searchParams.forEach((value, key) => url.searchParams.set(key, value));

  const headers: HeadersInit = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const contentType = req.headers.get("content-type");
  if (contentType) {
    headers["Content-Type"] = contentType;
  }

  const res = await fetch(url.toString(), {
    method: req.method,
    headers,
    body: req.method !== "GET" && req.method !== "HEAD"
      ? await req.text()
      : undefined,
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as DELETE,
};
