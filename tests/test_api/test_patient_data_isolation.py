"""Audit hackathon 2026-11-14 — cách ly dữ liệu liều + ảnh giữa bệnh nhân.

Trước sửa: GET /doses và 4 route ảnh chỉ gác bằng X-Internal-Secret (header do
proxy Next tự gắn) → ai gọi được FE cũng đọc lịch thuốc/ẢNH (PHI) của bệnh
nhân khác và gửi ảnh thay họ. Postgres thật.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.api.security import INTERNAL_SECRET_HEADER
from backend.config import get_settings
from backend.db.base import SessionLocal, engine
from backend.db.models import Account, CaregiverLink, DoseEvent, PhotoVerification
from backend.main import app
from backend.services.auth import create_access_token


def _db_ok() -> bool:
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_ok(), reason="Cần Postgres thật")


@pytest_asyncio.fixture
async def ctx(tmp_path):
    tag = uuid.uuid4().hex[:8]
    a_pid, b_pid = f"iso-a-{tag}", f"iso-b-{tag}"
    a_acc, b_acc, cg_acc = f"acc-a-{tag}", f"acc-b-{tag}", f"acc-cg-{tag}"
    anh = tmp_path / "a.jpg"
    anh.write_bytes(b"\xff\xd8\xff" + b"0" * 20)
    db = SessionLocal()
    for acc, pid in ((a_acc, a_pid), (b_acc, b_pid), (cg_acc, None)):
        db.add(Account(id=acc, full_name="t", email=f"{acc}@example.com", password_hash="x",
                       role="patient", status="active", patient_id=pid))
    gio = datetime.now(UTC)
    dose = DoseEvent(prescription_id="p", patient_id=a_pid, scheduled_at=gio, window_start=gio - timedelta(minutes=30),
                     window_end=gio + timedelta(minutes=30), status="PENDING",
                     expected_items=[{"ten_thuoc": "X", "dang_thuoc": "Viên nén", "so_vien": 1}])
    db.add(dose)
    db.flush()
    pv = PhotoVerification(dose_event_id=dose.id, patient_id=a_pid, attempt=1, expected_by_form={}, detected_by_form={},
                           ket_qua="khop", thong_bao="ok", image_path=str(anh))
    db.add(pv)
    db.add(CaregiverLink(caregiver_account_id=cg_acc, patient_id=a_pid, relationship="Con", status="accepted"))
    db.commit()
    ids = {"dose": dose.id, "pv": pv.id, "a_pid": a_pid}
    tok = {
        "a": create_access_token(sub=a_acc, role="patient", patient_id=a_pid),
        "b": create_access_token(sub=b_acc, role="patient", patient_id=b_pid),
        "cg": create_access_token(sub=cg_acc, role="patient"),
    }
    db.close()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t",
                           headers={INTERNAL_SECRET_HEADER: get_settings().internal_auth_secret}) as c:
        yield c, ids, tok
    db = SessionLocal()
    db.query(PhotoVerification).filter(PhotoVerification.patient_id == a_pid).delete()
    db.query(DoseEvent).filter(DoseEvent.patient_id == a_pid).delete()
    db.query(CaregiverLink).filter(CaregiverLink.patient_id == a_pid).delete()
    db.query(Account).filter(Account.id.in_([a_acc, b_acc, cg_acc])).delete(synchronize_session=False)
    db.commit()
    db.close()


def _urls(ids):
    return [
        f"/api/v1/doses?patient_id={ids['a_pid']}",
        f"/api/v1/photo-verifications/{ids['pv']}",
        f"/api/v1/doses/{ids['dose']}/photo-verifications",
        f"/api/v1/photo-verifications/{ids['pv']}/image",
    ]


@pytest.mark.asyncio
async def test_khong_token_bi_401(ctx):
    c, ids, _ = ctx
    for u in _urls(ids):
        assert (await c.get(u)).status_code == 401, u
    r = await c.post(f"/api/v1/doses/{ids['dose']}/photo", files={"file": ("a.jpg", b"x", "image/jpeg")})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_benh_nhan_khac_bi_403_ke_ca_gui_anh(ctx):
    c, ids, tok = ctx
    h = {"Authorization": f"Bearer {tok['b']}"}
    for u in _urls(ids):
        assert (await c.get(u, headers=h)).status_code == 403, u
    r = await c.post(f"/api/v1/doses/{ids['dose']}/photo", headers=h,
                     files={"file": ("a.jpg", b"x", "image/jpeg")})
    assert r.status_code == 403
    db = SessionLocal()
    assert db.query(PhotoVerification).filter_by(dose_event_id=ids["dose"]).count() == 1  # không tạo thêm
    db.close()


@pytest.mark.asyncio
async def test_chu_so_huu_va_nguoi_than_duoc_doc(ctx):
    c, ids, tok = ctx
    for who in ("a", "cg"):
        h = {"Authorization": f"Bearer {tok[who]}"}
        for u in _urls(ids):
            assert (await c.get(u, headers=h)).status_code == 200, (who, u)
