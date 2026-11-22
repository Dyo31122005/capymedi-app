import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { REFRESH_COOKIE_NAME, REFRESH_COOKIE_OPTIONS } from "../login/route";

// TASK-024 (api-contracts.md §1c-5) - nut "Tham quan". BFF proxy giong
// /api/auth/login: refresh_token vao httpOnly cookie (giu phien sau F5),
// access_token tra ve body cho client giu trong memory. Frontend KHONG biet
// email/mat khau tai khoan khach - backend tu chon theo role.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// GET: frontend hoi truoc de an/hien nut. Loi mang -> coi nhu tat, khong
// chan trang dang nhap.
export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/guest-login`, { cache: "no-store" });
    if (!res.ok) return NextResponse.json({ enabled: false, roles: [] });
    return NextResponse.json(await res.json());
  } catch {
    return NextResponse.json({ enabled: false, roles: [] });
  }
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  if (body?.role !== "doctor" && body?.role !== "patient") {
    return NextResponse.json({ detail: "Vai trò tham quan không hợp lệ" }, { status: 400 });
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${API_BASE}/api/v1/auth/guest-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: body.role }),
    });
  } catch {
    return NextResponse.json(
      { detail: "Không thể kết nối máy chủ đăng nhập. Vui lòng thử lại sau." },
      { status: 503 },
    );
  }
  const data = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok) {
    return NextResponse.json(data ?? { detail: "Chế độ tham quan hiện không khả dụng" }, {
      status: backendResponse.status,
    });
  }

  const { refresh_token: refreshToken, ...clientSafeData } = data;
  const cookieStore = await cookies();
  cookieStore.set(REFRESH_COOKIE_NAME, refreshToken, REFRESH_COOKIE_OPTIONS);

  return NextResponse.json(clientSafeData);
}
