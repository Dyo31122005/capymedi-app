"""TASK-CAPY-17 (hook PATCH /doses) + TASK-CAPY-19 (companion-api) tren Postgres that.

Tu skip khi khong co DB. CI `lint-and-test` khong co Postgres -> chay local/staging.
"""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import (  # noqa: E402
    Account,
    CaregiverLink,
    Companion,
    CompanionCareDay,
    DoseEvent,
    Patient,
    PatientRewardAccount,
    PatientRewardEvent,
    PhotoVerification,
    SystemAuditLog,
)
from backend.services.auth import create_access_token  # noqa: E402
from backend.services.companion import service as companion_service  # noqa: E402
from backend.services.reward_ledger import ngay_vn  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


@pytest.fixture
def bn():
    """(patient_id, headers benh nhan, caregiver_account_id, headers nguoi than co link)."""
    s = uuid.uuid4().hex[:8]
    pid, acct, cg = f"capy-api-{s}", f"capy-api-acct-{s}", f"capy-api-cg-{s}"
    db = SessionLocal()
    try:
        db.add(Account(id=acct, full_name="BN", email=f"{acct}@example.local", password_hash="x",
                       role="patient", status="active", patient_id=pid))
        db.add(Account(id=cg, full_name="NT", email=f"{cg}@example.local", password_hash="x",
                       role="caregiver", status="active"))
        db.add(Patient(id=pid, full_name="Bệnh nhân companion api"))
        db.add(CaregiverLink(caregiver_account_id=cg, patient_id=pid, relationship="con", status="accepted"))
        db.commit()
    finally:
        db.close()
    h_bn = {"Authorization": f"Bearer {create_access_token(sub=acct, role='patient', patient_id=pid)}"}
    h_cg = {"Authorization": f"Bearer {create_access_token(sub=cg, role='caregiver')}"}
    yield pid, h_bn, h_cg
    db = SessionLocal()
    try:
        ids = [r.id for r in db.query(DoseEvent.id).filter(DoseEvent.patient_id == pid)]
        if ids:
            db.query(SystemAuditLog).filter(SystemAuditLog.target.in_(ids)).delete(synchronize_session=False)
        for m in (CompanionCareDay, Companion, PatientRewardEvent, PatientRewardAccount, PhotoVerification,
                  DoseEvent, CaregiverLink):
            db.query(m).filter(m.patient_id == pid).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id == pid).delete(synchronize_session=False)
        db.query(Account).filter(Account.id.in_((acct, cg))).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.fixture
def bat(monkeypatch, bn):
    """Bat companion CHI cho benh nhan cua test (allowlist)."""
    s = get_settings()
    monkeypatch.setattr(s, "companion_enabled", True)
    monkeypatch.setattr(s, "companion_allowlist", bn[0])
    monkeypatch.setattr(s, "dose_runtime_mode", "legacy")


def _lieu(pid: str, status: str = "PENDING", bao_cao: datetime | None = None) -> str:
    hen = datetime.now(UTC)
    db = SessionLocal()
    try:
        d = DoseEvent(prescription_id="presc-capy-api", patient_id=pid, scheduled_at=hen,
                      window_start=hen - timedelta(minutes=30), window_end=hen + timedelta(minutes=30),
                      status=status, expected_items=[], first_reported_at=bao_cao)
        db.add(d)
        db.commit()
        return d.id
    finally:
        db.close()


def _care_days(pid: str) -> list[int]:
    db = SessionLocal()
    try:
        return [r.units for r in db.query(CompanionCareDay).filter(CompanionCareDay.patient_id == pid)]
    finally:
        db.close()


# --- TASK-CAPY-17: hook trong PATCH /doses/{id} -------------------------------


@pytest.mark.asyncio
async def test_patch_taken_lam_capy_lon_va_retry_khong_cong_doi(client, bn, bat):
    pid, h, _ = bn
    dose = _lieu(pid)
    r1 = await client.patch(f"/api/v1/doses/{dose}", json={"status": "TAKEN"}, headers=h)
    r2 = await client.patch(f"/api/v1/doses/{dose}", json={"status": "TAKEN"}, headers=h)
    assert r1.status_code == r2.status_code == 200
    assert _care_days(pid) == [100]


@pytest.mark.asyncio
async def test_co_tat_thi_hook_khong_ghi_gi(client, bn):
    pid, h, _ = bn
    dose = _lieu(pid)
    assert (await client.patch(f"/api/v1/doses/{dose}", json={"status": "TAKEN"}, headers=h)).status_code == 200
    db = SessionLocal()
    try:
        assert db.get(Companion, pid) is None and _care_days(pid) == []
    finally:
        db.close()


@pytest.mark.asyncio
async def test_hook_loi_khong_lam_hong_xac_nhan_lieu(client, bn, bat, monkeypatch):
    pid, h, _ = bn
    dose = _lieu(pid)

    def no(*_a, **_kw):
        raise RuntimeError("companion hong")

    monkeypatch.setattr(companion_service, "tinh_lai_ngay", no)
    r = await client.patch(f"/api/v1/doses/{dose}", json={"status": "TAKEN"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "TAKEN"
    db = SessionLocal()
    try:
        row = db.get(DoseEvent, dose)
        assert row.status == "TAKEN" and row.first_reported_at is not None
        assert db.query(SystemAuditLog).filter(SystemAuditLog.target == dose).count() == 1
    finally:
        db.close()
    assert _care_days(pid) == []


@pytest.mark.asyncio
async def test_awaiting_chi_lon_khi_nguoi_than_duyet(client, bn, bat):
    pid, _, h_cg = bn
    dose = _lieu(pid, "AWAITING_CAREGIVER", bao_cao=datetime.now(UTC))
    assert _care_days(pid) == []
    r = await client.patch(f"/api/v1/doses/{dose}", json={"status": "TAKEN"}, headers=h_cg)
    assert r.status_code == 200
    assert _care_days(pid) == [100]


# --- TASK-CAPY-19: companion-api ----------------------------------------------


@pytest.mark.asyncio
async def test_get_khi_tat(client, bn):
    r = await client.get("/api/v1/companion/me", headers=bn[1])
    assert r.status_code == 200
    assert r.json()["enabled"] is False and r.json()["unavailable_reason"] == "FEATURE_OFF"


@pytest.mark.asyncio
async def test_chi_benh_nhan_goi_duoc(client, bn):
    r = await client.get("/api/v1/companion/me", headers=bn[2])
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_doc_thuan_va_khong_lo_don_vi(client, bn, bat):
    db = SessionLocal()
    truoc = db.scalar(select(func.count()).select_from(Companion))
    db.close()
    r = await client.get("/api/v1/companion/me", headers=bn[1])
    db = SessionLocal()
    sau = db.scalar(select(func.count()).select_from(Companion))
    db.close()
    body = r.json()
    assert r.status_code == 200 and truoc == sau
    assert body["enabled"] is True and body["stage"] == 1 and body["stage_key"] == "CAPY_SO_SINH"
    assert not any("unit" in k or "growth" in k for k in body)


@pytest.mark.asyncio
async def test_dat_ten_va_tat_thi_409(client, bn, bat, monkeypatch):
    h = bn[1]
    r = await client.patch("/api/v1/companion/me", json={"name": "  Bơ  "}, headers=h)
    assert r.status_code == 200 and r.json()["name"] == "Bơ"
    assert (await client.patch("/api/v1/companion/me", json={"name": "   "}, headers=h)).status_code == 422
    monkeypatch.setattr(get_settings(), "companion_enabled", False)
    assert (await client.patch("/api/v1/companion/me", json={"name": "Bơ"}, headers=h)).status_code == 409


@pytest.mark.asyncio
async def test_ack_idempotent_va_chan_giai_doan_chua_toi(client, bn, bat):
    h = bn[1]
    assert (await client.post("/api/v1/companion/me/celebrations/2/ack", headers=h)).status_code == 422
    assert (await client.post("/api/v1/companion/me/celebrations/1/ack", headers=h)).status_code == 204
    assert (await client.post("/api/v1/companion/me/celebrations/1/ack", headers=h)).status_code == 204


@pytest.mark.asyncio
async def test_events(client, bn):
    h = bn[1]
    assert (await client.post("/api/v1/companion/me/events", json={"event": "FEED_TAP"}, headers=h)).status_code == 202
    assert (await client.post("/api/v1/companion/me/events", json={"event": "HACK"}, headers=h)).status_code == 422


# --- TASK-CAPY-26 / QA-03: fallback "anh sai het luot, khong co nguoi than" ----


def _anh(dose_id: str, pid: str, ket_qua: str, attempt: int) -> None:
    db = SessionLocal()
    try:
        db.add(PhotoVerification(dose_event_id=dose_id, patient_id=pid, attempt=attempt, expected_by_form={},
                                 detected_by_form={}, ket_qua=ket_qua, thong_bao="test"))
        db.commit()
    finally:
        db.close()


def _lieu_fallback(pid: str) -> str:
    """Trang thai sau khi verifier chot fallback: TAKEN, co first_reported_at, 3 anh lech, KHONG audit."""
    dose = _lieu(pid, "TAKEN", bao_cao=datetime.now(UTC))
    for i in (1, 2, 3):
        _anh(dose, pid, "lech", i)
    return dose


def _tinh_hom_nay(pid: str) -> None:
    db = SessionLocal()
    try:
        companion_service.tinh_lai_ngay(db, patient_id=pid, ngay=ngay_vn(datetime.now(UTC)))
        db.commit()
    finally:
        db.close()


def _audit(dose_id: str) -> list[str]:
    db = SessionLocal()
    try:
        return [r.action.split(" ")[0] for r in db.query(SystemAuditLog).filter(SystemAuditLog.target == dose_id)]
    finally:
        db.close()


def _so_dong_diem(pid: str) -> int:
    db = SessionLocal()
    try:
        return db.query(PatientRewardEvent).filter(PatientRewardEvent.patient_id == pid).count()
    finally:
        db.close()


def test_anh_khop_duoc_tinh(bn, bat):
    pid = bn[0]
    dose = _lieu(pid, "TAKEN", bao_cao=datetime.now(UTC))
    _anh(dose, pid, "lech", 1)
    _anh(dose, pid, "khop", 2)
    _tinh_hom_nay(pid)
    assert _care_days(pid) == [100]


def test_fallback_anh_sai_khong_lam_capy_lon(bn, bat):
    pid = bn[0]
    _lieu_fallback(pid)
    _tinh_hom_nay(pid)
    assert _care_days(pid) == [0], "anh sai het luot khong phai bang chung da uong"


@pytest.mark.asyncio
async def test_fallback_roi_benh_nhan_xac_nhan_ro_rang_thi_duoc_tinh_va_khong_doi_diem(client, bn, bat):
    pid, h, _ = bn
    dose = _lieu_fallback(pid)
    _tinh_hom_nay(pid)
    diem_truoc = _so_dong_diem(pid)

    r1 = await client.patch(f"/api/v1/doses/{dose}", json={"status": "TAKEN"}, headers=h)
    assert r1.status_code == 200 and r1.json()["status"] == "TAKEN" and r1.json()["points_awarded"] == 0
    assert _care_days(pid) == [100]
    assert _audit(dose) == ["DOSE_EXPLICIT_CONFIRM"]
    assert _so_dong_diem(pid) == diem_truoc, "khong doi LP/SP"

    r2 = await client.patch(f"/api/v1/doses/{dose}", json={"status": "TAKEN"}, headers=h)  # gui trung
    assert r2.status_code == 200
    assert _audit(dose) == ["DOSE_EXPLICIT_CONFIRM"], "gui trung khong ghi them"
    assert _care_days(pid) == [100] and _so_dong_diem(pid) == diem_truoc


@pytest.mark.asyncio
async def test_nguoi_than_khong_the_xac_nhan_thay_lieu_fallback(client, bn, bat):
    pid, _, h_cg = bn
    dose = _lieu_fallback(pid)
    _tinh_hom_nay(pid)
    r = await client.patch(f"/api/v1/doses/{dose}", json={"status": "TAKEN"}, headers=h_cg)
    assert r.status_code == 200
    assert _audit(dose) == [] and _care_days(pid) == [0]


@pytest.mark.asyncio
async def test_xac_nhan_lai_lieu_fallback_ngay_cu_khong_lam_capy_lon(client, bn, bat):
    """Review PR #11 (2026-11-14): xac nhan lai mot lieu fallback cua 3 ngay truoc
    khong duoc ghi DOSE_EXPLICIT_CONFIRM hay tinh lai tien do cho ngay cu."""
    pid, h, _ = bn
    hen = datetime.now(UTC) - timedelta(days=3)
    db = SessionLocal()
    try:
        d = DoseEvent(prescription_id="presc-capy-api", patient_id=pid, scheduled_at=hen,
                      window_start=hen - timedelta(minutes=30), window_end=hen + timedelta(minutes=30),
                      status="TAKEN", expected_items=[], first_reported_at=hen)
        db.add(d)
        db.commit()
        dose = d.id
    finally:
        db.close()
    for i in (1, 2, 3):
        _anh(dose, pid, "lech", i)
    r = await client.patch(f"/api/v1/doses/{dose}", json={"status": "TAKEN"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "TAKEN"
    assert _audit(dose) == []
    assert _care_days(pid) == []
