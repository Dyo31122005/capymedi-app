// Ban sao access_token TRONG BO NHO cho cac ham fetch khong nam trong React
// (lib/doses.ts...). AuthProvider ghi vao day moi lan render, KHONG luu
// localStorage/sessionStorage (giu dung chinh sach "token chi trong memory",
// xem lib/auth.tsx). Audit hackathon 2026-11-14: GET /doses va cac route anh
// gio doi JWT de chan doc/ghi du lieu benh nhan khac.
let accessTokenHienTai: string | null = null;

export function datAccessToken(token: string | null): void {
  accessTokenHienTai = token;
}

export function headerXacThuc(token?: string | null): Record<string, string> {
  const t = token ?? accessTokenHienTai;
  return t ? { Authorization: `Bearer ${t}` } : {};
}

// ---------------------------------------------------------------------------
// Tu lam moi access_token khi het han (2026-11-14).
//
// access_token song 60 phut va AuthProvider chi lam moi 1 lan luc mount. Truoc
// khi GET /doses va cac route anh doi JWT thi khong sao; tu khi doi JWT, benh
// nhan de app mo qua 60 phut roi bam "Chup anh xac nhan" se nhan 401 cho toi
// khi tai lai trang - hong dung luong chinh cua san pham. `fetchCoXacThuc` gap
// 401 thi lam moi token qua cookie refresh (httpOnly) roi goi lai DUNG 1 lan.
// ---------------------------------------------------------------------------
type HamLamMoiToken = () => Promise<string | null>;

let hamLamMoi: HamLamMoiToken | null = null;
let dangLamMoi: Promise<string | null> | null = null;

/** AuthProvider dang ky ham goi /api/auth/refresh + cap nhat state. */
export function datHamLamMoiToken(fn: HamLamMoiToken | null): void {
  hamLamMoi = fn;
}

/** Nhieu request cung gap 401 thi chi goi /api/auth/refresh MOT lan. */
export function lamMoiAccessToken(): Promise<string | null> {
  if (!hamLamMoi) return Promise.resolve(null);
  if (!dangLamMoi) {
    dangLamMoi = hamLamMoi()
      .catch(() => null)
      .finally(() => {
        dangLamMoi = null;
      });
  }
  return dangLamMoi;
}

/**
 * `fetch` kem header Authorization; gap 401 thi lam moi token va goi lai 1 lan.
 * Body phai dung lai duoc (chuoi, FormData, Blob) - khong dung voi stream.
 * `token` (tuy chon) uu tien hon token trong bo nho cho lan goi dau.
 */
export async function fetchCoXacThuc(
  input: string,
  init: RequestInit = {},
  token?: string | null,
): Promise<Response> {
  const goi = (t?: string | null) =>
    fetch(input, {
      ...init,
      headers: {
        ...((init.headers as Record<string, string> | undefined) ?? {}),
        ...headerXacThuc(t),
      },
    });
  const res = await goi(token);
  if (res.status !== 401) return res;
  const moi = await lamMoiAccessToken();
  return moi ? goi(moi) : res;
}
