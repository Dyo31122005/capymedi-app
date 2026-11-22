// fetchCoXacThuc (2026-11-14): gap 401 thi lam moi access_token qua cookie
// refresh roi goi lai DUNG 1 lan; nhieu request cung 401 chi refresh 1 lan.
// Chay: node --experimental-strip-types tests/access-token.test.mts
import assert from "node:assert/strict";

import { datAccessToken, datHamLamMoiToken, fetchCoXacThuc } from "../src/lib/access-token.ts";

type Call = { url: string; auth: string | undefined };

function giaFetch(hopLe: () => string) {
  const calls: Call[] = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    const auth = (init?.headers as Record<string, string> | undefined)?.Authorization;
    calls.push({ url, auth });
    return new Response(null, { status: auth === `Bearer ${hopLe()}` ? 200 : 401 });
  }) as typeof fetch;
  return calls;
}

// 1. Token con han -> goi 1 lan, khong refresh.
{
  let soLanRefresh = 0;
  const calls = giaFetch(() => "t1");
  datAccessToken("t1");
  datHamLamMoiToken(async () => {
    soLanRefresh += 1;
    return "t2";
  });
  const res = await fetchCoXacThuc("/api/doses?patient_id=p");
  assert.equal(res.status, 200);
  assert.equal(calls.length, 1);
  assert.equal(soLanRefresh, 0);
}

// 2. Token het han -> 401 -> refresh -> goi lai voi token moi -> 200.
{
  let hopLe = "t-moi";
  const calls = giaFetch(() => hopLe);
  datAccessToken("t-cu");
  datHamLamMoiToken(async () => "t-moi");
  const res = await fetchCoXacThuc("/api/doses/1/photo", { method: "POST", body: "x" });
  assert.equal(res.status, 200);
  assert.deepEqual(
    calls.map((c) => c.auth),
    ["Bearer t-cu", "Bearer t-moi"],
  );
  hopLe = "";
}

// 3. Refresh that bai (cookie het han) -> tra lai chinh response 401, khong lap.
{
  const calls = giaFetch(() => "khong-bao-gio");
  datAccessToken("t-cu");
  datHamLamMoiToken(async () => null);
  const res = await fetchCoXacThuc("/api/doses?patient_id=p");
  assert.equal(res.status, 401);
  assert.equal(calls.length, 1);
}

// 4. Nhieu request cung 401 -> chi goi /api/auth/refresh MOT lan.
{
  let soLanRefresh = 0;
  giaFetch(() => "t-moi");
  datAccessToken("t-cu");
  datHamLamMoiToken(async () => {
    soLanRefresh += 1;
    await new Promise((r) => setTimeout(r, 10));
    return "t-moi";
  });
  const ket = await Promise.all([fetchCoXacThuc("/a"), fetchCoXacThuc("/b"), fetchCoXacThuc("/c")]);
  assert.deepEqual(
    ket.map((r) => r.status),
    [200, 200, 200],
  );
  assert.equal(soLanRefresh, 1);
}

// 5. Header cua nguoi goi (Content-Type) duoc giu nguyen khi gan Authorization.
{
  let header: Record<string, string> | undefined;
  globalThis.fetch = (async (_url: string, init?: RequestInit) => {
    header = init?.headers as Record<string, string>;
    return new Response(null, { status: 200 });
  }) as typeof fetch;
  datAccessToken("t1");
  await fetchCoXacThuc("/x", { headers: { "Content-Type": "application/json" } });
  assert.deepEqual(header, { "Content-Type": "application/json", Authorization: "Bearer t1" });
}

console.log("access-token: 5 nhom kiem tra deu dat");
