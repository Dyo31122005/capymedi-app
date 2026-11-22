// Gio Viet Nam cho moi phep tinh "hom nay" o frontend (2026-11-14).
//
// `new Date().toISOString().slice(0, 10)` la ngay UTC: tu 0h toi 7h sang gio VN
// no tra ve HOM QUA (vd ngay bat dau phac do mac dinh, ngay sinh toi da). Ham
// nay luon tra ngay theo Asia/Ho_Chi_Minh, bat ke may chu Next (UTC) hay thiet
// bi nguoi dung dat mui gio nao.
export const VN_TZ = "Asia/Ho_Chi_Minh";

const DINH_DANG_NGAY_VN = new Intl.DateTimeFormat("en-CA", {
  timeZone: VN_TZ,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** Ngay (YYYY-MM-DD) theo gio Viet Nam cua thoi diem `moc` (mac dinh: bay gio). */
export function ngayVN(moc: Date = new Date()): string {
  return DINH_DANG_NGAY_VN.format(moc);
}
