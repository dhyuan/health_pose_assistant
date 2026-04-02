import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const url = `${BACKEND_URL}/api/v1/admin/devices/${id}/stream`;

  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return NextResponse.json(body, { status: res.status });
  }

  // Stream the MJPEG body through to the browser
  return new Response(res.body, {
    status: 200,
    headers: {
      "Content-Type":
        res.headers.get("Content-Type") ||
        "multipart/x-mixed-replace; boundary=frame",
      "Cache-Control": "no-cache, no-store, must-revalidate",
    },
  });
}
