// Server-side proxy cho /api/v1/companion/* (companion-api, api-contracts.md §3b,
// ADR-0016) - cung mau voi app/api/rewards/[...path]/route.ts: chi chuyen tiep
// Authorization, backend tu lay patient_id tu JWT. Khong gan X-Internal-Secret.

const BACKEND_URL =
  process.env.BACKEND_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Chi cho phep dung cac endpoint da biet (chan ghep URL toi endpoint bat ky).
const HOP_LE: Array<{ re: RegExp; methods: ReadonlyArray<string> }> = [
  { re: /^me$/, methods: ["GET", "PATCH"] },
  { re: /^me\/events$/, methods: ["POST"] },
  { re: /^me\/celebrations\/[1-9]\/ack$/, methods: ["POST"] },
];

async function chuyenTiep(request: Request, path: string[], method: string): Promise<Response> {
  const duongDan = path.join("/");
  if (!HOP_LE.some((r) => r.re.test(duongDan) && r.methods.includes(method))) {
    return Response.json({ detail: "Không tìm thấy endpoint" }, { status: 404 });
  }
  const authorization = request.headers.get("authorization");
  const upstream = await fetch(`${BACKEND_URL}/api/v1/companion/${duongDan}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(authorization ? { Authorization: authorization } : {}),
    },
    ...(method === "GET" ? {} : { body: await request.text() }),
  });
  // 204 (ack) khong co body - Response khong cho phep body voi 204.
  if (upstream.status === 204) return new Response(null, { status: 204 });
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, { params }: Ctx) {
  return chuyenTiep(request, (await params).path, "GET");
}
export async function PATCH(request: Request, { params }: Ctx) {
  return chuyenTiep(request, (await params).path, "PATCH");
}
export async function POST(request: Request, { params }: Ctx) {
  return chuyenTiep(request, (await params).path, "POST");
}
