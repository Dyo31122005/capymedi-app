"""TASK-CAPY-14/15: slot_summary + companion.service tren Postgres that.

Tu skip khi khong co DB (cung pattern tests/test_dose_status_update.py). Job
`lint-and-test` cua CI khong co Postgres -> phai chay local/staging.
"""

import sys
import threading
import time as time_mod
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Companion, CompanionCareDay, DoseEvent  # noqa: E402
from backend.services.companion import service  # noqa: E402
from backend.services.companion.errors import GiaiDoanKhongHopLeError  # noqa: E402
from backend.services.scheduling.slot_summary import RuntimeKhongHoTroError, liet_ke_slot_ngay  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")

D = date(2026, 11, 10)
_VN = timedelta(hours=7)


def _luc(ngay: date, gio: int, phut: int = 0) -> datetime:
    """Thoi diem UTC cua `gio:phut` gio VN ngay `ngay`."""
    return datetime(ngay.year, ngay.month, ngay.day, gio, phut, tzinfo=UTC) - _VN


@pytest.fixture
def pid():
    patient_id = f"capy-svc-{uuid.uuid4().hex[:8]}"
    yield patient_id
    db = SessionLocal()
    try:
        for model in (CompanionCareDay, Companion, DoseEvent):
            db.query(model).filter(model.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _lieu(pid: str, gio: int, status: str = "PENDING", bao_cao: datetime | None = None, ngay: date = D) -> str:
    db = SessionLocal()
    try:
        hen = _luc(ngay, gio)
        dose = DoseEvent(
            prescription_id="presc-capy-svc",
            patient_id=pid,
            scheduled_at=hen,
            window_start=hen - timedelta(minutes=30),
            window_end=hen + timedelta(minutes=30),
            status=status,
            expected_items=[],
            first_reported_at=bao_cao,
        )
        db.add(dose)
        db.commit()
        return dose.id
    finally:
        db.close()


def _dat(dose_id: str, status: str, bao_cao: datetime | None = None) -> None:
    db = SessionLocal()
    try:
        dose = db.get(DoseEvent, dose_id)
        dose.status = status
        if bao_cao is not None and dose.first_reported_at is None:
            dose.first_reported_at = bao_cao
        db.commit()
    finally:
        db.close()


def _tinh(pid: str, ngay: date = D) -> service.KetQuaTinhLai:
    db = SessionLocal()
    try:
        kq = service.tinh_lai_ngay(db, patient_id=pid, ngay=ngay)
        db.commit()
        return kq
    finally:
        db.close()


def _units(pid: str, ngay: date = D) -> int | None:
    db = SessionLocal()
    try:
        dong = db.get(CompanionCareDay, (pid, ngay))
        return dong.units if dong else None
    finally:
        db.close()


# --- slot_summary (TASK-CAPY-14) ----------------------------------------------


def test_slot_summary_theo_ngay_vn_va_giu_cancelled(pid):
    _lieu(pid, 6, "TAKEN", bao_cao=_luc(D, 6, 10))  # 06:00 VN = 23:00 UTC hom truoc
    _lieu(pid, 20, "CANCELLED")
    _lieu(pid, 8, ngay=D + timedelta(days=1))  # ngay khac -> khong lay
    db = SessionLocal()
    try:
        facts = liet_ke_slot_ngay(db, patient_id=pid, ngay=D)
    finally:
        db.close()
    assert sorted(f.status for f in facts) == ["CANCELLED", "TAKEN"]
    taken = next(f for f in facts if f.status == "TAKEN")
    assert taken.ngay_hen == D and taken.ngay_bao_cao == D


def test_slot_summary_tu_choi_runtime_v2(pid, monkeypatch):
    monkeypatch.setattr(get_settings(), "dose_runtime_mode", "v2")
    db = SessionLocal()
    try:
        with pytest.raises(RuntimeKhongHoTroError):
            liet_ke_slot_ngay(db, patient_id=pid, ngay=D)
    finally:
        db.close()


# --- tinh_lai_ngay (TASK-CAPY-15) ---------------------------------------------


def test_ngay_khong_co_lieu_khong_tao_dong(pid):
    kq = _tinh(pid)
    assert kq.units_sau == 0 and _units(pid) is None


def test_idempotent_goi_10_lan(pid):
    _lieu(pid, 8, "TAKEN", bao_cao=_luc(D, 8, 5))
    _lieu(pid, 20)
    ket_qua = {_tinh(pid).units_sau for _ in range(10)}
    assert ket_qua == {50} and _units(pid) == 50


def test_dung_phac_do_giua_ngay_sua_tinh_thieu(pid):
    """Hang 5b: 08:00 xong (50), 20:00 bi CANCELLED -> tinh lai = 100."""
    _lieu(pid, 8, "TAKEN", bao_cao=_luc(D, 8, 5))
    toi = _lieu(pid, 20)
    assert _tinh(pid).units_sau == 50
    _dat(toi, "CANCELLED")
    kq = _tinh(pid)
    assert kq.units_sau == 100 and kq.eligible_truoc == 2 and kq.eligible_sau == 1


def test_sua_phac_do_xoa_lieu_tuong_lai_sua_tinh_thieu(pid):
    """Hang 7b: lieu PENDING tuong lai bi XOA khi sua phac do -> ra khoi n."""
    _lieu(pid, 8, "TAKEN", bao_cao=_luc(D, 8, 5))
    toi = _lieu(pid, 20)
    assert _tinh(pid).units_sau == 50
    db = SessionLocal()
    db.delete(db.get(DoseEvent, toi))
    db.commit()
    db.close()
    assert _tinh(pid).units_sau == 100


def test_tang_lieu_sau_khi_xong_chi_tang_khong_giam(pid):
    """Hang 7a / T-1: tinh du co gioi han, khong tut truoc mat nguoi dung."""
    _lieu(pid, 8, "TAKEN", bao_cao=_luc(D, 8, 5))
    assert _tinh(pid).units_sau == 100
    _lieu(pid, 20)
    kq = _tinh(pid)
    assert kq.units_sau == 100 and kq.eligible_sau == 2 and kq.completed_sau == 1


def test_sua_taken_thanh_missed_khong_thu_hoi(pid):
    """Hang 14 / T-3."""
    lieu = _lieu(pid, 8, "TAKEN", bao_cao=_luc(D, 8, 5))
    assert _tinh(pid).units_sau == 100
    _dat(lieu, "MISSED")
    assert _tinh(pid).units_sau == 100


def test_bao_cao_tre_khong_tinh(pid):
    """Hang 8: uong ngay D, bao cao ngay D+1."""
    _lieu(pid, 8, "DELAYED", bao_cao=_luc(D + timedelta(days=1), 9))
    assert _tinh(pid).units_sau == 0


def test_awaiting_chi_tinh_khi_duyet_taken(pid):
    """Hang 11a/11b: AWAITING chua tinh; duyet TAKEN ngay sau van tinh cho ngay
    hen vi bao cao dau tien (first_reported_at) roi vao ngay hen."""
    duyet = _lieu(pid, 21, "AWAITING_CAREGIVER", bao_cao=_luc(D, 21, 10))
    tu_choi = _lieu(pid, 8, "AWAITING_CAREGIVER", bao_cao=_luc(D, 8, 10))
    assert _tinh(pid).units_sau == 0
    _dat(duyet, "TAKEN")
    _dat(tu_choi, "MISSED")
    assert _tinh(pid).units_sau == 50


# --- lay_trang_thai / ack ------------------------------------------------------


def test_lay_trang_thai_doc_thuan_va_khong_lo_don_vi(pid, monkeypatch):
    monkeypatch.setattr(get_settings(), "companion_enabled", True)
    monkeypatch.setattr(get_settings(), "companion_rollout_percentage", 100)  # TASK-CAPY-16: can cohort
    db = SessionLocal()
    try:
        truoc = db.scalar(select(func.count()).select_from(Companion))
        tt = service.lay_trang_thai(db, pid)
        db.commit()
        sau = db.scalar(select(func.count()).select_from(Companion))
    finally:
        db.close()
    assert truoc == sau, "GET khong duoc tao dong"
    assert tt["stage"] == 1 and tt["progress_pct"] == 0 and tt["pending_celebration_stage"] is None
    assert not any("unit" in k or "growth" in k for k in tt)


def test_lay_trang_thai_tat_mac_dinh(pid):
    db = SessionLocal()
    try:
        assert service.lay_trang_thai(db, pid) == {"enabled": False, "unavailable_reason": "FEATURE_OFF"}
    finally:
        db.close()


def test_le_lon_len_va_ack_idempotent(pid, monkeypatch):
    monkeypatch.setattr(get_settings(), "companion_enabled", True)
    monkeypatch.setattr(get_settings(), "companion_rollout_percentage", 100)  # TASK-CAPY-16: can cohort
    for i in range(3):  # 3 ngay cham soc tron = 300 -> giai doan 2
        ngay = D + timedelta(days=i)
        _lieu(pid, 8, "TAKEN", bao_cao=_luc(ngay, 8, 5), ngay=ngay)
        _tinh(pid, ngay)
    db = SessionLocal()
    try:
        assert service.lay_trang_thai(db, pid)["pending_celebration_stage"] == 2
        with pytest.raises(GiaiDoanKhongHopLeError):
            service.xac_nhan_da_mung(db, pid, 3)
        service.xac_nhan_da_mung(db, pid, 2)
        service.xac_nhan_da_mung(db, pid, 2)
        db.commit()
        assert service.lay_trang_thai(db, pid)["pending_celebration_stage"] is None
    finally:
        db.close()


# --- Postgres: FOR UPDATE serialize theo benh nhan ----------------------------


def test_hai_transaction_dong_thoi_khong_tinh_thieu(pid):
    """Khong khoa: A va B moi ben chi thay lieu cua minh -> ca hai ghi 50 ->
    tinh thieu. Co khoa: B cho A commit roi dem lai -> 100."""
    sang = _lieu(pid, 8)
    toi = _lieu(pid, 20)
    _tinh(pid)  # tao san dong companion (de B chac chan cho tren FOR UPDATE)

    a = SessionLocal()
    a.get(DoseEvent, sang).status = "TAKEN"
    a.get(DoseEvent, sang).first_reported_at = _luc(D, 8, 5)
    service.tinh_lai_ngay(a, patient_id=pid, ngay=D)  # giu khoa, CHUA commit

    loi: list[BaseException] = []

    def b_chay() -> None:
        b = SessionLocal()
        try:
            b.get(DoseEvent, toi).status = "TAKEN"
            b.get(DoseEvent, toi).first_reported_at = _luc(D, 20, 5)
            service.tinh_lai_ngay(b, patient_id=pid, ngay=D)
            b.commit()
        except BaseException as exc:  # noqa: BLE001 - chuyen loi ve thread chinh
            loi.append(exc)
        finally:
            b.close()

    t = threading.Thread(target=b_chay)
    t.start()
    time_mod.sleep(0.5)
    assert t.is_alive(), "B phai dang cho khoa cua A"
    a.commit()
    a.close()
    t.join(timeout=10)
    assert not loi, loi
    assert _units(pid) == 100
