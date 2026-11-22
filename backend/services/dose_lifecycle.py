"""Chot cac lieu con PENDING sau khi da sang ngay moi thanh MISSED.

VI SAO CAN: truoc job nay KHONG co gi trong he thong chuyen PENDING -> MISSED.
Ca hai cho tung phai ne tranh dieu do deu da ghi lai trong comment cua chinh
chung: dose_push_reminder.py ("lieu ton dong tu hom truoc - khong ai doi
status thanh MISSED") va photo_verification/verifier.py ("he thong chua co
job quet tu chuyen PENDING qua han sang MISSED"). Hau qua do duoc tren DB
that ngay 2026-08-31: 122 tren 142 lieu PENDING da qua window va nam do vinh
vien, lam ty le tuan thu hien thi 88% trong khi thuc te la 23%.

MOC CHOT LA "QUA NGAY MOI GIO VN", KHONG PHAI "QUA WINDOW":
mot lieu 20:00 ma 20:45 benh nhan moi xac nhan la UONG MUON (DELAYED), khong
phai bo lieu. Chot ngay khi het window (+30 phut) se cuop mat co hoi xac nhan
muon do. Quy tac nay khop voi bo may trang thai V2 da hien thuc san
(scheduling/dose_state.py::_same_scheduled_local_day) - hai bo dung CHUNG mot
dinh nghia de khi cutover sang V2 khong bi lech.

AWAITING_CAREGIVER CO Y KHONG BI CHOT (quyet dinh san pham 2026-08-31): lieu
ket o trang thai do la vi NGUOI THAN chua bam duyet sau khi anh khong khop 3
lan, khong phai vi benh nhan bo thuoc. Chot thanh MISSED se phat nham nguoi.
No duoc dem rieng thanh chi so "cho nguoi than duyet" tren giao dien.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DoseEvent
from backend.services.reward_ledger import ngay_vn

logger = logging.getLogger("dose_lifecycle")

# Chi trang thai nay moi bi chot - moi trang thai con lai hoac da chot ket qua
# (TAKEN/DELAYED/MISSED/CANCELLED) hoac dang cho nguoi khac (AWAITING_CAREGIVER).
TRANG_THAI_CHOT_DUOC = "PENDING"
TRANG_THAI_SAU_KHI_CHOT = "MISSED"


def _as_utc(value: datetime) -> datetime:
    """Doc moc thoi gian da luu, ke ca ban naive cua adapter SQLite trong test.

    Postgres tra ve TIMESTAMPTZ nen da co tzinfo; SQLite lam rot tzinfo du gia
    tri ghi vao von da la UTC. Cung idiom voi doctor_takeover_timeout._as_utc().
    """
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def qua_ngay_moi(scheduled_at: datetime, now: datetime) -> bool:
    """True khi `now` da sang ngay khac (GIO VIET NAM) so voi ngay cua lieu.

    BAT BUOC so theo ngay VN chu khong phai ngay UTC: mot lieu 06:00 gio VN
    duoc luu la 23:00 UTC cua HOM TRUOC, so theo ngay UTC se ket luan nham la
    da qua ngay ngay tu buoi sang cung ngay.

    Dung lai ngay_vn() cua reward_ledger thay vi tu tinh mui gio - diem thuong
    da gom lieu theo ngay bang ham do, hai cho lech dinh nghia mot ngay se cho
    ra "lieu bi chot MISSED nhung van duoc tinh diem cua ngay hom sau".
    """
    return ngay_vn(_as_utc(now)) > ngay_vn(_as_utc(scheduled_at))


def chot_nhan_xac_nhan(window_end: datetime, now: datetime) -> str:
    """Xac nhan uong thuoc luc `now` thi mang nhan TAKEN hay DELAYED.

    Trong window (+-30 phut quanh gio hen) la TAKEN; sau window_end la DELAYED
    - BR-2.2. `now == window_end` van tinh la trong window, giu dung bien
    khong chat cua bieu thuc goc trong verifier.py.

    Ham nay ton tai de HAI duong xac nhan dung chung mot quy tac. Duong chup
    anh (photo_verification/verifier.py) da lam dung tu truoc; duong tu khai
    (PATCH /doses/{id}) thi gan thang chuoi client gui len nen KHONG BAO GIO
    sinh ra DELAYED - do la bug lam man Lich su luon bao "0 lan xac nhan muon".

    KHONG phan biet "tre trong ngay" voi "tre nhieu ngay" o day: lieu de sang
    ngay moi da bi chot_lieu_qua_han() chuyen thanh MISSED truoc do, nen khi
    ham nay chay thi lieu chac chan van con trong ngay cua no.
    """
    return "TAKEN" if _as_utc(now) <= _as_utc(window_end) else "DELAYED"


def chot_lieu_qua_han(db: Session, *, now: datetime | None = None) -> int:
    """Chuyen moi lieu PENDING cua nhung ngay truoc sang MISSED. Tra ve so lieu
    vua doi o LAN CHAY NAY (0 neu khong con gi de chot).

    KHONG commit - de nguoi goi quyet dinh ranh gioi giao dich, cung idiom voi
    reward_ledger._award(), push.py va telegram.py. Ham nay doi cot `status`
    cua nhieu dong, va cung mot lan chay co the can nam chung giao dich voi
    viec khac cua nguoi goi (vd backfill vua chot vua ghi bao cao); tu commit
    ben trong se cat doi giao dich do va lam ham khong con dung lai duoc o
    workflow nao khac ngoai job dung mot minh.

    Idempotent theo dinh nghia: lieu da doi sang MISSED khong con khop dieu
    kien PENDING nen lan chay sau khong dem lai.

    Loc so bo bang SQL (`status = PENDING` va `scheduled_at < now`) roi moi
    kiem tra moc ngay VN trong Python. Co y khong dung moc ngay vao thang SQL:
    lam vay phai nhan doi hang so mui gio dang nam trong reward_ledger, ma hai
    ban sao lech nhau la dung loi ma job nay sinh ra de sua. Tap ung vien sau
    lan backfill dau tien chi con nhieu nhat mot ngay lieu ton dong.
    """
    now = _as_utc(now or datetime.now(UTC))

    ung_vien = db.execute(
        select(DoseEvent).where(
            DoseEvent.status == TRANG_THAI_CHOT_DUOC,
            DoseEvent.scheduled_at < now,
        )
    ).scalars()

    da_chot = 0
    for lieu in ung_vien:
        if not qua_ngay_moi(lieu.scheduled_at, now):
            continue
        lieu.status = TRANG_THAI_SAU_KHI_CHOT
        da_chot += 1

    if da_chot:
        db.flush()
        logger.info("Da chot %d lieu qua han thanh MISSED (chua commit)", da_chot)
    return da_chot


# --- Quy tac cap nhat lieu qua PATCH /doses/{id} (TASK-CAPY-04, ADR-0016) ----
#
# specs/business-rules.md muc 8. BR-8.1/8.3/8.5 la quy tac ky thuat (cho Tech
# Lead duyet). BR-8.2 (khoang bao cao tre) la quyet dinh LAM SANG chua duoc
# duyet -> chi ap dung khi nguoi goi truyen ap_dung_khoang_bao_cao=True, tuc la
# khi settings.dose_provisional_policy_enabled bat (mac dinh TAT o production).

# PROVISIONAL - BR-8.2, cho PM + bac si chot. Khong co hieu luc khi co tat.
LATE_REPORT_DAYS = 3

# BR-8.1: chi hai nhan nay duoc dat qua PATCH. CANCELLED chi sinh khi dung phac
# do (BR-1.4); PENDING/DELAYED/AWAITING_CAREGIVER do he thong tu dat.
TRANG_THAI_DUOC_PATCH = frozenset({"TAKEN", "MISSED"})

# Trang thai nghia la "da co bao cao da uong" - dung cho first_reported_at
# (BR-8.5) va de nhan biet gui lai trung (no-op).
TRANG_THAI_DA_BAO_CAO = frozenset({"TAKEN", "DELAYED", "AWAITING_CAREGIVER"})
_TRANG_THAI_DA_UONG = frozenset({"TAKEN", "DELAYED"})

LY_DO_KHONG_CHO_DAT = "Trạng thái này không được cập nhật trực tiếp"
LY_DO_QUA_HAN = "Liều đã quá thời hạn ghi nhận, vui lòng liên hệ bác sĩ"


@dataclass(frozen=True)
class QuyetDinhCapNhat:
    """Ket qua kiem tra mot PATCH. `trang_thai_moi` chi co nghia khi CHO_PHEP."""

    hanh_dong: Literal["CHO_PHEP", "NO_OP", "TU_CHOI"]
    trang_thai_moi: str | None = None
    ly_do: str | None = None


def kiem_tra_cap_nhat_lieu(
    *,
    current_status: str,
    target_status: str,
    actor_role: str,
    is_owner: bool,
    scheduled_at: datetime,
    window_end: datetime,
    now: datetime,
    ap_dung_khoang_bao_cao: bool,
) -> QuyetDinhCapNhat:
    """Quyet dinh mot PATCH trang thai lieu la cho phep / no-op / tu choi.

    Ham thuan, khong cham DB. CHI quyet dinh ve ho so lam sang - khong biet gi
    ve diem thuong (route tu quyet dinh LP/SP sau khi da ghi trang thai).

    `is_owner`: nguoi goi chinh la benh nhan so huu lieu. Phan quyen theo
    quan he (caregiver link, bac si) da duoc route kiem tra TRUOC ham nay.
    """
    if target_status not in TRANG_THAI_DUOC_PATCH:
        return QuyetDinhCapNhat("TU_CHOI", ly_do=LY_DO_KHONG_CHO_DAT)

    # Gui lai dung y dinh hien tai -> no-op. Rieng "da uong": TAKEN hay DELAYED
    # deu la da uong roi, khong duoc suy lai thanh DELAYED khi retry (V-5).
    if target_status == "TAKEN" and current_status in _TRANG_THAI_DA_UONG:
        return QuyetDinhCapNhat("NO_OP")
    if target_status == current_status:
        return QuyetDinhCapNhat("NO_OP")

    if current_status == "AWAITING_CAREGIVER":
        # Duyet anh khong khop la viec cua nguoi khac, khong phai benh nhan tu duyet.
        if is_owner:
            return QuyetDinhCapNhat("TU_CHOI", ly_do=_ly_do_chuyen(current_status, target_status))
    elif current_status not in {"PENDING", "MISSED", "TAKEN", "DELAYED"}:
        # CANCELLED (bac si dung phac do) hoac gia tri la -> khong mo lai qua PATCH.
        return QuyetDinhCapNhat("TU_CHOI", ly_do=_ly_do_chuyen(current_status, target_status))
    elif ap_dung_khoang_bao_cao and actor_role != "doctor":
        han_cuoi = ngay_vn(_as_utc(now)) - timedelta(days=LATE_REPORT_DAYS)
        if ngay_vn(_as_utc(scheduled_at)) < han_cuoi:
            return QuyetDinhCapNhat("TU_CHOI", ly_do=LY_DO_QUA_HAN)

    trang_thai_moi = chot_nhan_xac_nhan(window_end, now) if target_status == "TAKEN" else target_status
    return QuyetDinhCapNhat("CHO_PHEP", trang_thai_moi=trang_thai_moi)


def _ly_do_chuyen(tu: str, sang: str) -> str:
    return f"Không thể chuyển liều từ {tu} sang {sang}"


def danh_dau_da_bao_cao(dose: DoseEvent, now: datetime) -> bool:
    """BR-8.5: ghi first_reported_at DUNG MOT LAN khi lieu vao trang thai "da
    co bao cao da uong". Khong bao gio ghi de - day la moc lam sang "luc nao co
    bao cao dau tien", cung la can cu xet "cung ngay" cho companion.

    Goi SAU khi da gan `dose.status`. Tra ve True neu vua ghi."""
    if dose.first_reported_at is not None or dose.status not in TRANG_THAI_DA_BAO_CAO:
        return False
    dose.first_reported_at = _as_utc(now)
    return True


def bao_cao_cung_ngay(dose: DoseEvent, now: datetime) -> bool:
    """Bao cao "da uong" cua lieu nay co roi vao chinh ngay hen (gio VN) khong.

    Dua tren first_reported_at (lan bao cao DAU TIEN) neu co, khong thi `now` -
    de nguoi than duyet mot lieu AWAITING_CAREGIVER sau nhieu ngay khong bi tinh
    la bao cao tre khi chinh benh nhan da bao cao dung ngay."""
    moc = dose.first_reported_at or now
    return ngay_vn(_as_utc(moc)) == ngay_vn(_as_utc(dose.scheduled_at))
