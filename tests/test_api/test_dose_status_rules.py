"""TASK-CAPY-03 - regression baseline cho V-1..V-6 cua PATCH /api/v1/doses/{id}.

Moi test assert HANH VI MONG MUON sau khi sua (BR-8.1..BR-8.7 trong
specs/business-rules.md muc 8, ADR-0016), KHONG phai hanh vi hien tai. Tren
code hien tai cac test nay DUOC KY VONG DO - TASK-CAPY-05/08 se lam chung
xanh. Khong merge rieng file nay vao main khi con do.

Cung pattern voi tests/test_dose_status_update.py: FastAPI TestClient + DB
Postgres that, tu skip khi khong co DB. Luu y: job `lint-and-test` cua CI
KHONG co service Postgres (.github/workflows/ci.yml) nen o CI cac test nay bi
SKIP - phai chay tren Postgres that (local docker hoac staging).

LATE_REPORT_DAYS (BR-8.2) chua chot (de xuat 3, cho PM + bac si). Test V-4
dung lieu cach 10 ngay - ngoai moi gia tri hop ly <= 7 - de khong phu thuoc
con so cu the."""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import (  # noqa: E402
    Account,
    DoseEvent,
    Patient,
    PatientRewardAccount,
    PatientRewardEvent,
    SystemAuditLog,
)
from backend.services import reward_catalog as catalog  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


@pytest.fixture
def benh_nhan():
    """(patient_id, account_id, headers) cua mot benh nhan rieng cho tung test;
    don sach moi thu lien quan sau khi test xong."""
    suffix = uuid.uuid4().hex[:8]
    patient_id = f"capy-rt-{suffix}"
    account_id = f"capy-rt-acct-{suffix}"
    db = SessionLocal()
    try:
        db.add(
            Account(
                id=account_id,
                full_name="Capy regression test",
                email=f"{account_id}@example.local",
                password_hash="not-a-real-hash",
                role="patient",
                status="active",
                patient_id=patient_id,
            )
        )
        db.add(Patient(id=patient_id, full_name="Bệnh nhân capy regression"))
        db.commit()
    finally:
        db.close()
    token = create_access_token(sub=account_id, role="patient", patient_id=patient_id)
    yield patient_id, account_id, {"Authorization": f"Bearer {token}"}

    db = SessionLocal()
    try:
        dose_ids = [d.id for d in db.query(DoseEvent.id).filter(DoseEvent.patient_id == patient_id)]
        if dose_ids:
            db.query(SystemAuditLog).filter(SystemAuditLog.target.in_(dose_ids)).delete(synchronize_session=False)
        for model in (PatientRewardEvent, PatientRewardAccount, DoseEvent):
            db.query(model).filter(model.patient_id == patient_id).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.fixture
def chinh_sach_tam(monkeypatch):
    """Bat quy tac PROVISIONAL BR-8.2/BR-8.7a (mac dinh TAT, chua duoc duyet)."""
    monkeypatch.setattr(get_settings(), "dose_provisional_policy_enabled", True)


def _tao_lieu(patient_id: str, *, lui: timedelta = timedelta(0), status: str = "PENDING") -> str:
    """Tao 1 dose_event hen luc (bay gio - lui), window +-30 phut."""
    hen = datetime.now(UTC) - lui
    db = SessionLocal()
    try:
        dose = DoseEvent(
            prescription_id="presc-capy-rt",
            patient_id=patient_id,
            scheduled_at=hen,
            window_start=hen - timedelta(minutes=30),
            window_end=hen + timedelta(minutes=30),
            status=status,
            expected_items=[],
        )
        db.add(dose)
        db.commit()
        return dose.id
    finally:
        db.close()


def _doc_lieu(dose_id: str) -> DoseEvent:
    db = SessionLocal()
    try:
        return db.get(DoseEvent, dose_id)
    finally:
        db.close()


def _doi_lich_ve_qua_khu(dose_id: str, gio: int) -> None:
    """Mo phong thoi gian troi qua: day ca lich + window cua lieu lui `gio` tieng."""
    db = SessionLocal()
    try:
        dose = db.get(DoseEvent, dose_id)
        for cot in ("scheduled_at", "window_start", "window_end"):
            setattr(dose, cot, getattr(dose, cot) - timedelta(hours=gio))
        db.commit()
    finally:
        db.close()


def _tong_diem_phat(patient_id: str) -> int:
    db = SessionLocal()
    try:
        return sum(
            e.points_delta
            for e in db.query(PatientRewardEvent).filter(
                PatientRewardEvent.patient_id == patient_id,
                PatientRewardEvent.event_type == catalog.EVENT_DOSE_METHOD_PENALTY,
            )
        )
    finally:
        db.close()


def _so_dong_cong_diem(patient_id: str) -> int:
    db = SessionLocal()
    try:
        return (
            db.query(PatientRewardEvent)
            .filter(PatientRewardEvent.patient_id == patient_id, PatientRewardEvent.points_delta > 0)
            .count()
        )
    finally:
        db.close()


# --- V-1: PATCH nhan chuoi status tuy y --------------------------------------


@pytest.mark.asyncio
async def test_v1_status_ngoai_taken_missed_bi_tu_choi(client, benh_nhan):
    patient_id, _, headers = benh_nhan
    dose_id = _tao_lieu(patient_id)

    response = await client.patch(f"/api/v1/doses/{dose_id}", json={"status": "KHONG_HOP_LE"}, headers=headers)

    assert response.status_code == 422, "BR-8.1: chi nhan TAKEN|MISSED"
    assert _doc_lieu(dose_id).status == "PENDING", "status khong hop le khong duoc ghi vao DB"


# --- V-2: benh nhan tu huy lieu (CANCELLED) ----------------------------------


@pytest.mark.asyncio
async def test_v2_benh_nhan_khong_tu_dat_cancelled(client, benh_nhan):
    """CANCELLED chi sinh khi bac si dung phac do (BR-1.4). Neu benh nhan tu dat
    duoc, lieu bi loai khoi mau so diem (reward_ledger.py) VA ho so lam sang sai."""
    patient_id, _, headers = benh_nhan
    dose_id = _tao_lieu(patient_id)

    response = await client.patch(f"/api/v1/doses/{dose_id}", json={"status": "CANCELLED"}, headers=headers)

    assert response.status_code == 422
    assert _doc_lieu(dose_id).status == "PENDING"


# --- V-3: PENDING -> MISSED -> TAKEN ne muc tru tu khai ----------------------


@pytest.mark.asyncio
async def test_v3_missed_roi_taken_tru_dung_cho_va_dung_muc(client, benh_nhan):
    """Muc tru tu khai (PCT_SELF_REPORT_NO_PHOTO) phai gan voi lan xac nhan
    "da uong", xac dinh theo nguoi goi (BR-8.7) - khong theo previous_status.

    Lan theo code hien tai (dose_routes.py::_xac_dinh_ty_le_thuong +
    reward_ledger::apply_confirmation_method_penalty): bam MISSED tu PENDING da
    ghi ngay dong phat (bo qua lieu bi tru SP du khong duoc cong gi), roi
    MISSED -> TAKEN cong du diem va bao "+20" thay vi muc tu khai."""
    patient_id, _, headers = benh_nhan
    dose_id = _tao_lieu(patient_id)  # trong window, 1 lieu duy nhat trong ngay
    muc_tru = catalog.POINTS_DOSE_ON_TIME - round(
        catalog.POINTS_DOSE_ON_TIME * catalog.PCT_SELF_REPORT_NO_PHOTO / 100
    )

    r1 = await client.patch(f"/api/v1/doses/{dose_id}", json={"status": "MISSED"}, headers=headers)
    assert r1.status_code == 200
    assert _tong_diem_phat(patient_id) == 0, "bo qua lieu khong duoc bi tru diem"

    r2 = await client.patch(f"/api/v1/doses/{dose_id}", json={"status": "TAKEN"}, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "TAKEN"
    assert r2.json()["points_awarded"] == catalog.POINTS_DOSE_ON_TIME - muc_tru, "phai bang muc tu khai truc tiep"
    assert _tong_diem_phat(patient_id) == -muc_tru, "dung mot khoan tru tu khai"


# --- V-4: xac nhan lui ngay ---------------------------------------------------


@pytest.mark.asyncio
async def test_v4_bao_cao_ngoai_khoang_cho_phep_bi_tu_choi(client, benh_nhan, chinh_sach_tam):
    """BR-8.2 (cho duyet): ngoai LATE_REPORT_DAYS thi 422, khong ghi gi."""
    patient_id, _, headers = benh_nhan
    dose_id = _tao_lieu(patient_id, lui=timedelta(days=10), status="MISSED")

    response = await client.patch(f"/api/v1/doses/{dose_id}", json={"status": "TAKEN"}, headers=headers)

    assert response.status_code == 422
    assert _doc_lieu(dose_id).status == "MISSED"
    assert _so_dong_cong_diem(patient_id) == 0


@pytest.mark.asyncio
async def test_v4_bao_cao_tre_trong_khoang_duoc_ghi_nhung_khong_cong_diem(client, benh_nhan, chinh_sach_tam):
    """Ho so lam sang PHAI duoc ghi (khong hy sinh do chinh xac y te), nhung bao
    cao khac ngay hen nhan 0 LP/SP (BR-8.7, cho Tech Lead duyet)."""
    patient_id, _, headers = benh_nhan
    dose_id = _tao_lieu(patient_id, lui=timedelta(days=1), status="MISSED")

    response = await client.patch(f"/api/v1/doses/{dose_id}", json={"status": "TAKEN"}, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "DELAYED", "BR-2.2/BR-8.4 khong doi: qua window_end -> DELAYED"
    assert response.json()["points_awarded"] == 0
    assert _so_dong_cong_diem(patient_id) == 0


# --- V-5: gui lai TAKEN sau window ha TAKEN xuong DELAYED --------------------


@pytest.mark.asyncio
async def test_v5_gui_lai_taken_la_no_op(client, benh_nhan):
    """Retry (mang chap chon) sau window_end khong duoc doi TAKEN thanh DELAYED
    hay cong/tru them diem (BR-8.3)."""
    patient_id, _, headers = benh_nhan
    dose_id = _tao_lieu(patient_id)

    r1 = await client.patch(f"/api/v1/doses/{dose_id}", json={"status": "TAKEN"}, headers=headers)
    assert r1.status_code == 200 and r1.json()["status"] == "TAKEN"
    phat_truoc = _tong_diem_phat(patient_id)

    _doi_lich_ve_qua_khu(dose_id, gio=2)  # gio da qua window_end
    r2 = await client.patch(f"/api/v1/doses/{dose_id}", json={"status": "TAKEN"}, headers=headers)

    assert r2.status_code == 200
    assert r2.json()["status"] == "TAKEN", "retry khong duoc ha xuong DELAYED"
    assert r2.json()["points_awarded"] == 0
    assert _tong_diem_phat(patient_id) == phat_truoc


# --- V-6: PATCH khong ghi audit ----------------------------------------------


@pytest.mark.asyncio
async def test_v6_doi_trang_thai_ghi_audit(client, benh_nhan):
    """BR-1.5 / BR-8.6: moi lan doi trang thai lieu ghi system_audit_logs, quy
    duoc trach nhiem cho nguoi goi."""
    patient_id, account_id, headers = benh_nhan
    dose_id = _tao_lieu(patient_id)

    response = await client.patch(f"/api/v1/doses/{dose_id}", json={"status": "TAKEN"}, headers=headers)
    assert response.status_code == 200

    db = SessionLocal()
    try:
        dong = db.query(SystemAuditLog).filter(SystemAuditLog.target == dose_id).all()
    finally:
        db.close()
    assert len(dong) == 1
    assert dong[0].actor_id == account_id
    assert dong[0].actor_role == "patient"
