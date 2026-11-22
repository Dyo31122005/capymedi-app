// Chon man hinh sau mot lan xac nhan lieu (TASK-CAPY-23, ADR-0016 BR-8.10,
// planning §3.2). HAM THUAN - khong import gi, de test bang node --experimental-strip-types.
//
// Man an mung la quyet dinh HIEN THI cua client; viec Capy co lon hay khong
// la quyet dinh cua SERVER (companion.service). Hai thu co the khac nhau co chu dich:
//  - FEED: chi khi lieu THUC SU vao TAKEN/DELAYED, cua HOM NAY, va (neu qua anh) anh KHOP.
//  - SUPPORTIVE: anh khong khop het luot (AWAITING_CAREGIVER hoac TAKEN khi khong co
//    nguoi than) - co the la uong nham thuoc, KHONG BAO GIO an mung.
//  - NEUTRAL: bao cao tre / bo qua lieu - chi toast.
//  - null: chua co ket qua nghiep vu (dang xu ly, can chup lai, loi he thong).

export type CareMomentKind = "FEED" | "SUPPORTIVE" | "NEUTRAL";

export type KetQuaXacNhan = {
  source: "SELF_REPORT" | "PHOTO";
  /** Trang thai lieu SAU khi xac nhan, do backend tra ve (khong suy tu HTTP 200). */
  resultStatus: string;
  scheduledAt: string;
  now: Date;
  /** Chi voi PHOTO. */
  matched?: boolean | null;
  nextAction?: string | null;
};

const DA_UONG = new Set(["TAKEN", "DELAYED"]);

export function cungNgayDiaPhuong(iso: string, now: Date): boolean {
  const d = new Date(iso);
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

export function chonLoaiManHinh(k: KetQuaXacNhan): CareMomentKind | null {
  if (k.source === "PHOTO") {
    if (k.matched === true) {
      if (!DA_UONG.has(k.resultStatus)) return null;
      return cungNgayDiaPhuong(k.scheduledAt, k.now) ? "FEED" : "NEUTRAL";
    }
    if (k.matched === false && k.nextAction === "CAREGIVER_REVIEW") return "SUPPORTIVE";
    return null; // RETAKE, dang xu ly, loi he thong, do tin cay thap
  }
  if (k.resultStatus === "AWAITING_CAREGIVER") return "SUPPORTIVE";
  if (DA_UONG.has(k.resultStatus))
    return cungNgayDiaPhuong(k.scheduledAt, k.now) ? "FEED" : "NEUTRAL";
  return "NEUTRAL"; // MISSED / bo qua lieu
}

/** Mon an ao theo buoi cua lieu - CHI la an du, khong bao gio la thuoc. */
export type CapyFood = "leaf" | "watermelon" | "orange";

export function monAnTheoBuoi(scheduledAt: string): CapyFood {
  const h = new Date(scheduledAt).getHours();
  if (h < 11) return "leaf";
  if (h < 16) return "watermelon";
  return "orange";
}

// --- Chong phat lai man cho an cho cung mot lieu (fedSlotIds) ------------------

const KHOA = "capy-fed-slots";

type Kho = Pick<Storage, "getItem" | "setItem">;

function docKho(kho: Kho | null, homNay: string): string[] {
  try {
    const raw = kho?.getItem(KHOA);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed?.day === homNay && Array.isArray(parsed.ids) ? parsed.ids : [];
  } catch {
    return [];
  }
}

/** True neu lieu nay da duoc cho an hom nay (tren may nay). Mat localStorage chi mat animation. */
export function daChoAn(doseId: string, now: Date, kho: Kho | null): boolean {
  return docKho(kho, now.toDateString()).includes(doseId);
}

export function danhDauDaChoAn(doseId: string, now: Date, kho: Kho | null): void {
  const homNay = now.toDateString();
  const ids = docKho(kho, homNay);
  if (ids.includes(doseId)) return;
  try {
    kho?.setItem(KHOA, JSON.stringify({ day: homNay, ids: [...ids, doseId] }));
  } catch {
    // private mode / bi chan - bo qua
  }
}
