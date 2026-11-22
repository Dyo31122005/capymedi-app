"""Service domain `companion` (TASK-CAPY-15, ADR-0016).

`tinh_lai_ngay` la HAM DUY NHAT ghi tien do. Tat dinh: dem lai n/k tu
dose_event qua scheduling.slot_summary roi luu units = GREATEST(cu, moi) - goi
1 lan hay 10 lan, tu hook (TASK-CAPY-17) hay job (TASK-CAPY-18), deu hoi tu
cung ket qua. Serialize theo benh nhan bang SELECT ... FOR UPDATE tren dong
`companion`: transaction den sau cho transaction truoc commit roi moi dem, nen
thay du lieu cua no (READ COMMITTED).

KHONG commit - de nguoi goi quyet dinh ranh gioi giao dich (cung idiom voi
reward_ledger._award, dose_lifecycle.chot_lieu_qua_han).

`lay_trang_thai` la DOC THUAN: khong tao, khong sua dong nao (D-6).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import Companion, CompanionCareDay
from backend.services.companion import progression
from backend.services.companion.errors import GiaiDoanKhongHopLeError, TenKhongHopLeError
from backend.services.dose_lifecycle import _as_utc
from backend.services.reward_ledger import ngay_vn
from backend.services.scheduling.slot_summary import (
    benh_nhan_co_bao_cao_tu,
    cap_benh_nhan_ngay_doi_trang_thai_tu,
    liet_ke_slot_ngay,
    runtime_ho_tro,
)

TEN_TOI_DA = 20


@dataclass(frozen=True)
class KetQuaTinhLai:
    """Truoc/sau cua 1 ngay - job doi soat dung de dem recovered_missing /
    schedule_adjusted (TASK-CAPY-18)."""

    ngay: date
    units_truoc: int
    units_sau: int
    eligible_truoc: int | None
    eligible_sau: int
    completed_truoc: int | None
    completed_sau: int


def _bay_gio() -> datetime:
    return datetime.now(UTC)


def _khoa_companion(db: Session, patient_id: str) -> Companion:
    """Tao dong companion neu chua co (an toan khi 2 request cung tao), roi
    khoa no FOR UPDATE. SQLite (test) bo qua FOR UPDATE - khong sao."""
    if db.get(Companion, patient_id) is None:
        try:
            with db.begin_nested():
                db.add(Companion(patient_id=patient_id, celebrated_stage=1))
                db.flush()
        except IntegrityError:
            pass  # dong kia da tao truoc - doc lai ben duoi
    return db.execute(
        select(Companion).where(Companion.patient_id == patient_id).with_for_update().execution_options(
            populate_existing=True
        )
    ).scalar_one()


def tinh_lai_ngay(db: Session, *, patient_id: str, ngay: date) -> KetQuaTinhLai:
    """Tinh lai tien do cua `patient_id` cho ngay VN `ngay`. Chi tang.

    Ngay khong co slot nao (n == 0) va chua co dong -> khong tao dong."""
    _khoa_companion(db, patient_id)
    db.flush()  # autoflush=False (backend/db/base.py): dem phai thay status vua gan

    n, k = progression.dem_ngay(liet_ke_slot_ngay(db, patient_id=patient_id, ngay=ngay))
    target = progression.day_units(k, n)

    dong = db.get(CompanionCareDay, (patient_id, ngay), populate_existing=True)
    if dong is None:
        if n == 0:
            return KetQuaTinhLai(ngay, 0, 0, None, 0, None, 0)
        dong = CompanionCareDay(patient_id=patient_id, care_date=ngay, units=target, eligible_count=n, completed_count=k)
        db.add(dong)
        ket_qua = KetQuaTinhLai(ngay, 0, target, None, n, None, k)
    else:
        ket_qua = KetQuaTinhLai(
            ngay, dong.units, max(dong.units, target), dong.eligible_count, n, dong.completed_count, k
        )
        dong.units = ket_qua.units_sau
        dong.eligible_count = n
        dong.completed_count = k
    dong.updated_at = _bay_gio()
    db.flush()
    return ket_qua


def tong_growth(db: Session, patient_id: str) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(CompanionCareDay.units), 0)).where(CompanionCareDay.patient_id == patient_id)
        )
        or 0
    )


def _trong_cohort(patient_id: str) -> bool:
    """Allowlist HOAC bucket on dinh sha256(patient_id) % 100 < pct - cung
    cach voi agent_v2_routes._in_rollout_percentage (khong nhay vao/ra khi tang pct)."""
    settings = get_settings()
    allowlist = {x.strip() for x in settings.companion_allowlist.split(",") if x.strip()}
    if patient_id in allowlist:
        return True
    pct = settings.companion_rollout_percentage
    if pct <= 0:
        return False
    return int(hashlib.sha256(patient_id.encode("utf-8")).hexdigest(), 16) % 100 < pct


def ly_do_khong_kha_dung(patient_id: str) -> str | None:
    """None neu companion bat cho benh nhan nay; khong thi FEATURE_OFF /
    RUNTIME_UNSUPPORTED (ngoai cohort cung la FEATURE_OFF - khong lo cohort)."""
    if not get_settings().companion_enabled or not _trong_cohort(patient_id):
        return "FEATURE_OFF"
    if not runtime_ho_tro():
        return "RUNTIME_UNSUPPORTED"
    return None


def companion_bat_cho(patient_id: str) -> bool:
    """TASK-CAPY-16: co bat + trong cohort + runtime legacy/shadow."""
    return ly_do_khong_kha_dung(patient_id) is None


def lay_trang_thai(db: Session, patient_id: str) -> dict:
    """GET /companion/me (TASK-CAPY-19). DOC THUAN. Khong bao gio tra don vi noi bo."""
    ly_do = ly_do_khong_kha_dung(patient_id)
    if ly_do is not None:
        return {"enabled": False, "unavailable_reason": ly_do}

    growth = tong_growth(db, patient_id)
    stage = progression.stage_for(growth)
    companion = db.get(Companion, patient_id)
    da_mung = companion.celebrated_stage if companion else 1
    la_cuoi = stage >= progression.MAX_STAGE
    return {
        "enabled": True,
        "unavailable_reason": None,
        "stage": stage,
        "stage_key": progression.STAGE_KEYS[stage - 1],
        "stage_label": progression.STAGE_LABELS[stage - 1],
        "next_stage_key": None if la_cuoi else progression.STAGE_KEYS[stage],
        "next_stage_label": None if la_cuoi else progression.STAGE_LABELS[stage],
        "is_max_stage": la_cuoi,
        "progress_pct": progression.progress_pct(growth),
        "name": companion.name if companion else None,
        "pending_celebration_stage": stage if stage > da_mung else None,
    }


def xac_nhan_da_mung(db: Session, patient_id: str, stage: int) -> None:
    """Ack le lon len. Idempotent; chi tang celebrated_stage. KHONG commit."""
    hien_tai = progression.stage_for(tong_growth(db, patient_id))
    if stage < 1 or stage > hien_tai:
        raise GiaiDoanKhongHopLeError("Capy chưa tới giai đoạn này.")
    companion = _khoa_companion(db, patient_id)
    if companion.celebrated_stage < stage:
        companion.celebrated_stage = stage
        companion.updated_at = _bay_gio()


def dat_ten(db: Session, patient_id: str, name: str) -> None:
    """Dat ten Capy (1-20 ky tu sau khi bo khoang trang). KHONG commit."""
    ten = (name or "").strip()
    if not 1 <= len(ten) <= TEN_TOI_DA:
        raise TenKhongHopLeError(f"Tên Capy cần từ 1 đến {TEN_TOI_DA} ký tự.")
    companion = _khoa_companion(db, patient_id)
    companion.name = ten
    companion.updated_at = _bay_gio()


# --- Tich hop su kien thuoc (TASK-CAPY-17) -----------------------------------

logger = logging.getLogger("companion")


def ghi_nhan_tu_hook(db: Session, *, dose_event) -> None:
    """Goi tu PATCH /doses/{id} va verifier, TRUOC commit cua nguoi goi.

    Chay trong SAVEPOINT: loi companion chi rollback savepoint, xac nhan lieu
    (status, first_reported_at, audit, LP/SP) van commit binh thuong. Job doi
    soat (doi_soat_gan_day) bu lai sau. Tinh lai ngay HEN cua lieu - nguoi than
    duyet muon van tinh dung ngay benh nhan bao cao (growth_done xet
    first_reported_at). AWAITING_CAREGIVER tu nhien cho k khong doi."""
    if not companion_bat_cho(dose_event.patient_id):
        return
    db.flush()  # dam bao thay doi lieu da xuong DB TRUOC savepoint
    try:
        with db.begin_nested():
            # _as_utc nhu slot_summary/job: session Postgres khong phai UTC thi
            # scheduled_at mang offset +07 va ngay_vn se cong them 7h lan nua.
            tinh_lai_ngay(db, patient_id=dose_event.patient_id, ngay=ngay_vn(_as_utc(dose_event.scheduled_at)))
    except Exception:  # noqa: BLE001 - companion khong bao gio duoc chan ghi nhan lieu
        logger.exception(
            "companion_hook_failed patient_id=%s dose_id=%s", dose_event.patient_id, dose_event.id
        )


# --- Job doi soat (TASK-CAPY-18) ---------------------------------------------


@dataclass
class ThongKeDoiSoat:
    patients: int = 0
    days: int = 0
    recovered_missing: int = 0
    schedule_adjusted: int = 0
    errors: int = 0
    skipped_reason: str | None = field(default=None)


def _benh_nhan_co_care_day_tu(db: Session, tu_ngay: date) -> set[str]:
    return set(
        db.scalars(select(CompanionCareDay.patient_id).where(CompanionCareDay.care_date >= tu_ngay).distinct()).all()
    )


def doi_soat_gan_day(session_factory: Callable[[], Session], *, now: datetime | None = None) -> ThongKeDoiSoat:
    """Tinh lai tien do cho cac cap (benh nhan, ngay) co the da lech:
      1. Benh nhan co bao cao "da uong" lan dau trong `lookback` ngay -> hom qua + hom nay
         (bu hook loi o duong bao cao binh thuong).
      2. Benh nhan da co companion_care_day trong cua so -> hom qua + hom nay
         (lieu bi huy / xoa khi sua phac do: sua tinh thieu).
      3. Moi lieu doi trang thai qua PATCH trong `lookback` (vet audit) -> CHINH NGAY HEN
         cua lieu (nguoi than duyet AWAITING muon nhieu ngay).
    Khong quet toan bo lich su. Moi benh nhan 1 transaction rieng; loi cua
    benh nhan nay khong chan benh nhan khac. Idempotent (tinh_lai_ngay + GREATEST).

    GIOI HAN: neu job khong chay qua `companion_reconcile_lookback_days` ngay
    thi vet audit cu hon nam ngoai cua so -> dung CLI doi soat (TASK-CAPY-32)."""
    tk = ThongKeDoiSoat()
    settings = get_settings()
    if not settings.companion_enabled:
        tk.skipped_reason = "FEATURE_OFF"
    elif not runtime_ho_tro():
        tk.skipped_reason = "RUNTIME_UNSUPPORTED"
    if tk.skipped_reason:
        logger.info(json.dumps({"job": "doi_soat_companion", "skipped": tk.skipped_reason}))
        return tk

    now = now or _bay_gio()
    so_ngay = settings.companion_reconcile_lookback_days
    hom_nay = ngay_vn(now)
    cua_so = [hom_nay - timedelta(days=i) for i in range(so_ngay)]
    moc = now - timedelta(days=so_ngay)

    cap: dict[str, set[date]] = defaultdict(set)
    db = session_factory()
    try:
        for pid in benh_nhan_co_bao_cao_tu(db, moc=moc) | _benh_nhan_co_care_day_tu(db, min(cua_so)):
            cap[pid].update(cua_so)
        for pid, ngay in cap_benh_nhan_ngay_doi_trang_thai_tu(db, moc=moc):
            cap[pid].add(ngay)
    finally:
        db.close()

    for pid in sorted(cap):
        if not _trong_cohort(pid):
            continue
        tk.patients += 1
        db = session_factory()
        try:
            for ngay in sorted(cap[pid]):
                kq = tinh_lai_ngay(db, patient_id=pid, ngay=ngay)
                tk.days += 1
                if kq.units_sau <= kq.units_truoc:
                    continue
                if kq.completed_sau > (kq.completed_truoc or 0):
                    # Lieu da xac nhan ma tien do chua phan anh -> hook da bo lo.
                    tk.recovered_missing += 1
                    logger.warning(
                        json.dumps(
                            {"event": "companion_recovered_missing", "patient_id": pid, "care_date": ngay.isoformat()}
                        )
                    )
                elif kq.eligible_truoc is not None and kq.eligible_sau < kq.eligible_truoc:
                    tk.schedule_adjusted += 1
            db.commit()
        except Exception:  # noqa: BLE001 - 1 benh nhan loi khong duoc chan ca job
            db.rollback()
            tk.errors += 1
            logger.exception("companion_reconcile_patient_failed patient_id=%s", pid)
        finally:
            db.close()

    logger.info(json.dumps({"job": "doi_soat_companion", **{k: v for k, v in tk.__dict__.items() if v is not None}}))
    return tk
