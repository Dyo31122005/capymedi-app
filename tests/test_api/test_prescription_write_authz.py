"""Vá bảo mật 2026-11-14 — chỉ bác sĩ/admin được ghi phác đồ.

Trước sửa: POST /prescriptions, /approve, /reject, /stop chỉ gác bằng
X-Internal-Secret. Header đó do chính proxy Next tự gắn cho MỌI người gọi, nên
một bệnh nhân đã đăng nhập tự tạo rồi tự duyệt được phác đồ cho mình (vượt
Human-in-the-loop) và hệ thống sinh lịch uống thuốc không qua bác sĩ.

Sau sửa: 4 route trên đòi JWT role doctor/admin/super_admin, và doctor_id ghi
vào phác đồ lấy từ JWT bác sĩ chứ không tin `doctor_id` trong body. Postgres thật.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.api.security import INTERNAL_SECRET_HEADER
from backend.config import get_settings
from backend.db.base import SessionLocal, engine
from backend.db.models import Account, DoseEvent, Patient, Prescription
from backend.main import app
from backend.services.auth import create_access_token
from backend.services.drug_knowledge.v2_agent import get_v2_agent_knowledge_service


def _db_ok() -> bool:
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_ok(), reason="Cần Postgres thật")


@pytest_asyncio.fixture
async def ctx():
    tag = uuid.uuid4().hex[:8]
    pid = f"rx-authz-{tag}"
    patient_acc, doctor_acc = f"acc-pt-{tag}", f"acc-dr-{tag}"
    doctor_id = f"dr-{tag}"
    db = SessionLocal()
    db.add(Patient(id=pid, full_name="Bệnh nhân phân quyền"))
    db.add(Account(id=patient_acc, full_name="t", email=f"{patient_acc}@example.com", password_hash="x",
                   role="patient", status="active", patient_id=pid))
    db.add(Account(id=doctor_acc, full_name="t", email=f"{doctor_acc}@example.com", password_hash="x",
                   role="doctor", status="active", doctor_id=doctor_id))
    db.commit()
    secret = {INTERNAL_SECRET_HEADER: get_settings().internal_auth_secret}
    tok = {
        "patient": create_access_token(sub=patient_acc, role="patient", patient_id=pid),
        "doctor": create_access_token(sub=doctor_acc, role="doctor", doctor_id=doctor_id),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"client": client, "secret": secret, "tok": tok, "pid": pid, "doctor_id": doctor_id}
    db.query(DoseEvent).filter(DoseEvent.patient_id == pid).delete(synchronize_session=False)
    db.query(Prescription).filter(Prescription.patient_id == pid).delete(synchronize_session=False)
    db.query(Account).filter(Account.id.in_([patient_acc, doctor_acc])).delete(synchronize_session=False)
    db.query(Patient).filter(Patient.id == pid).delete(synchronize_session=False)
    db.commit()
    db.close()


def _headers(ctx, role: str | None) -> dict:
    h = dict(ctx["secret"])
    if role:
        h["Authorization"] = f"Bearer {ctx['tok'][role]}"
    return h


def _payload(ctx, doctor_id: str = "demo-doctor-01") -> dict:
    item = get_v2_agent_knowledge_service().catalog_items[0]
    return {
        "patient_id": ctx["pid"],
        "doctor_id": doctor_id,
        "items": [{"drug_id": item.drug_id, "ten_thuoc": item.ten_thuoc, "lieu_dung": "1 viên", "gio_nhac": ["08:00"]}],
    }


@pytest.mark.asyncio
async def test_tao_phac_do_khong_co_jwt_bi_tu_choi(ctx):
    res = await ctx["client"].post("/api/v1/prescriptions", json=_payload(ctx), headers=_headers(ctx, None))
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_benh_nhan_khong_tu_tao_phac_do_duoc(ctx):
    res = await ctx["client"].post("/api/v1/prescriptions", json=_payload(ctx), headers=_headers(ctx, "patient"))
    assert res.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("hanh_dong", ["approve", "reject", "stop"])
async def test_benh_nhan_khong_tu_duyet_tu_choi_dung_phac_do_duoc(ctx, hanh_dong):
    created = await ctx["client"].post("/api/v1/prescriptions", json=_payload(ctx), headers=_headers(ctx, "doctor"))
    assert created.status_code == 201
    res = await ctx["client"].post(
        f"/api/v1/prescriptions/{created.json()['id']}/{hanh_dong}",
        json={"doctor_id": "demo-doctor-01"},
        headers=_headers(ctx, "patient"),
    )
    assert res.status_code == 403
    db = SessionLocal()
    try:
        assert db.get(Prescription, created.json()["id"]).status == "draft"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_bac_si_tao_va_duyet_ghi_dung_bac_si_trong_jwt(ctx):
    """Body gửi doctor_id giả (FE luôn gửi `demo-doctor-01`) - backend phải ghi bác sĩ trong JWT."""
    created = await ctx["client"].post(
        "/api/v1/prescriptions", json=_payload(ctx, doctor_id="ke-mao-danh"), headers=_headers(ctx, "doctor")
    )
    assert created.status_code == 201
    assert created.json()["doctor_id"] == ctx["doctor_id"]
    approved = await ctx["client"].post(
        f"/api/v1/prescriptions/{created.json()['id']}/approve",
        json={"doctor_id": "ke-mao-danh"},
        headers=_headers(ctx, "doctor"),
    )
    assert approved.status_code == 200
    assert approved.json()["approved_by"] == ctx["doctor_id"]
