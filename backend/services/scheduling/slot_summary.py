"""Read API cua domain `scheduling` cho Capybara Companion (TASK-CAPY-14, ADR-0016).

Companion KHONG truy van thang `dose_event` (ADR-0002) - doc qua day. Module
chi tra DU KIEN (trang thai, ngay hen, ngay bao cao dau tien), khong biet gi
ve quy tac lon len; quy tac nam o backend/services/companion/progression.py.

Chi ho tro runtime phuc vu tu `dose_event` (`legacy`, `shadow` - xem
dose_routes.py: hai mode nay deu doc dose_event). Mode `v2` raise
RuntimeKhongHoTroError co chu dich thay vi am tham tra rong (D-9, TASK-CAPY-30).

Ngay dia phuong tinh bang reward_ledger.ngay_vn - CUNG dinh nghia ngay voi
diem thuong va job chot MISSED (dose_lifecycle.py), khong tu tinh mui gio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import DoseEvent, PhotoVerification, SystemAuditLog
from backend.services.dose_lifecycle import _as_utc
from backend.services.prescription.errors import VmecError
from backend.services.reward_ledger import ngay_vn

RUNTIME_HO_TRO = frozenset({"legacy", "shadow"})


class RuntimeKhongHoTroError(VmecError):
    """Companion chua ho tro dose_runtime_mode hien tai (v2)."""

    ma_loi = "COMPANION_RUNTIME_UNSUPPORTED"
    http_status = 409


@dataclass(frozen=True)
class SlotFact:
    """Du kien toi thieu cua 1 slot (1 dong dose_event). `ngay_bao_cao` la ngay
    VN cua first_reported_at, None neu chua tung co bao cao "da uong"."""

    status: str
    ngay_hen: date
    ngay_bao_cao: date | None
    # TASK-CAPY-26 / QA-03: TAKEN/DELAYED chi do fallback "anh sai het luot,
    # khong co nguoi than" (verifier.py) - CHUA co xac nhan ro rang nao.
    chi_fallback_anh: bool = False


def runtime_ho_tro() -> bool:
    return get_settings().dose_runtime_mode in RUNTIME_HO_TRO


def _kiem_tra_runtime() -> None:
    if not runtime_ho_tro():
        raise RuntimeKhongHoTroError("Companion chưa hỗ trợ dose runtime hiện tại.")


def _to_fact(
    status: str, scheduled_at: datetime, first_reported_at: datetime | None, chi_fallback_anh: bool = False
) -> SlotFact:
    return SlotFact(
        status=status,
        ngay_hen=ngay_vn(_as_utc(scheduled_at)),
        ngay_bao_cao=ngay_vn(_as_utc(first_reported_at)) if first_reported_at else None,
        chi_fallback_anh=chi_fallback_anh,
    )


# Vet audit cua mot xac nhan RO RANG "da uong" (BR-8.6): PATCH doi sang TAKEN/
# DELAYED (benh nhan tu khai, nguoi than/bac si duyet) hoac benh nhan xac nhan
# lai mot lieu fallback (DOSE_EXPLICIT_CONFIRM, dose_routes.py).
_AUDIT_XAC_NHAN_RO_RANG = (
    "DOSE_STATUS_CHANGE %to=TAKEN%",
    "DOSE_STATUS_CHANGE %to=DELAYED%",
    "DOSE_EXPLICIT_CONFIRM %",
)
_DA_UONG = ("TAKEN", "DELAYED")


def lieu_chi_fallback_anh(db: Session, dose_ids: list[str]) -> set[str]:
    """Tap lieu (trong `dose_ids`) da TAKEN/DELAYED ma CHI do fallback anh:
    co anh, KHONG anh nao khop, va KHONG co xac nhan ro rang nao trong audit.

    Dung du kien co san (photo_verification + system_audit_logs), khong them cot.
    Lieu chua tung chup anh (vd tu khai truoc P0, chua co audit) KHONG bi coi la
    fallback - giu tuong thich nguoc."""
    if not dose_ids:
        return set()
    anh = {
        dose_id: bool(co_khop)
        for dose_id, co_khop in db.execute(
            select(
                PhotoVerification.dose_event_id,
                func.max(case((PhotoVerification.ket_qua == "khop", 1), else_=0)),
            )
            .where(PhotoVerification.dose_event_id.in_(dose_ids))
            .group_by(PhotoVerification.dose_event_id)
        ).all()
    }
    nghi_ngo = [d for d, co_khop in anh.items() if not co_khop]
    if not nghi_ngo:
        return set()
    ro_rang = set(
        db.scalars(
            select(SystemAuditLog.target)
            .where(
                SystemAuditLog.target.in_(nghi_ngo),
                or_(*(SystemAuditLog.action.like(m) for m in _AUDIT_XAC_NHAN_RO_RANG)),
            )
            .distinct()
        ).all()
    )
    return set(nghi_ngo) - ro_rang


def liet_ke_slot_ngay(db: Session, *, patient_id: str, ngay: date) -> list[SlotFact]:
    """Moi slot cua benh nhan co NGAY HEN (gio VN) = `ngay`, KE CA CANCELLED
    (nguoi goi tu quyet dinh slot nao eligible). Slot da bi xoa khi sua phac do
    (generator._xoa_lieu_chua_toi_han) tu nhien khong con o day.

    Loc SQL theo khoang UTC rong +-1 ngay roi chot ngay VN trong Python - cung
    ly do voi dose_lifecycle.chot_lieu_qua_han: khong nhan doi hang so mui gio."""
    _kiem_tra_runtime()
    dau = datetime.combine(ngay - timedelta(days=1), time.min).replace(tzinfo=None)
    cuoi = datetime.combine(ngay + timedelta(days=2), time.min).replace(tzinfo=None)
    rows = [
        r
        for r in db.execute(
            select(DoseEvent.id, DoseEvent.status, DoseEvent.scheduled_at, DoseEvent.first_reported_at).where(
                DoseEvent.patient_id == patient_id,
                DoseEvent.scheduled_at >= _as_utc(dau),
                DoseEvent.scheduled_at < _as_utc(cuoi),
            )
        ).all()
        if ngay_vn(_as_utc(r.scheduled_at)) == ngay
    ]
    fallback = lieu_chi_fallback_anh(db, [r.id for r in rows if r.status in _DA_UONG])
    return [_to_fact(r.status, r.scheduled_at, r.first_reported_at, r.id in fallback) for r in rows]


def benh_nhan_co_bao_cao_tu(db: Session, *, moc: datetime) -> set[str]:
    """patient_id co it nhat 1 lieu duoc bao cao "da uong" lan dau tu `moc`.
    Dung cho job doi soat (TASK-CAPY-18); dua tren partial index migration 0064."""
    _kiem_tra_runtime()
    return set(
        db.scalars(
            select(DoseEvent.patient_id).where(DoseEvent.first_reported_at >= _as_utc(moc)).distinct()
        ).all()
    )


# Tien to action ma PATCH /doses/{id} ghi vao system_audit_logs (dose_routes.py,
# BR-8.6). Chi doc `target` (= dose_event.id) va `created_at` - khong parse noi dung.
_AUDIT_DOI_TRANG_THAI = "DOSE_STATUS_CHANGE %"
# Xac nhan lai lieu fallback (dose_routes.py) KHONG doi status/first_reported_at,
# nen job chi tim ra ngay do qua vet audit nay khi hook companion loi.
_AUDIT_XAC_NHAN_LAI = "DOSE_EXPLICIT_CONFIRM %"


def cap_benh_nhan_ngay_doi_trang_thai_tu(db: Session, *, moc: datetime) -> set[tuple[str, date]]:
    """(patient_id, ngay hen VN) cua moi lieu doi trang thai qua PATCH tu `moc`.

    Can cho job doi soat (TASK-CAPY-18): nguoi than duyet mot lieu
    AWAITING_CAREGIVER cua ngay D vao ngay D+5 -> lieu do lon len cho NGAY D,
    nam ngoai cua so "hom qua + hom nay". Neu hook loi luc duyet, chi vet audit
    (ghi CUNG transaction voi trang thai, khong nam trong savepoint companion)
    con lai de tim ra ngay D."""
    _kiem_tra_runtime()
    rows = db.execute(
        select(DoseEvent.patient_id, DoseEvent.scheduled_at)
        .join(SystemAuditLog, SystemAuditLog.target == DoseEvent.id)
        .where(
            or_(SystemAuditLog.action.like(_AUDIT_DOI_TRANG_THAI), SystemAuditLog.action.like(_AUDIT_XAC_NHAN_LAI)),
            SystemAuditLog.created_at >= _as_utc(moc),
        )
        .distinct()
    ).all()
    return {(pid, ngay_vn(_as_utc(hen))) for pid, hen in rows}
