"""Audit 2026-11-14 — cổng xác minh email (Postgres thật).

POST /auth/register trả access_token ngay cho tài khoản CHƯA xác minh; trước
sửa token đó gọi được mọi API (get_current_user không kiểm tra). Email xác minh
do Supabase Auth gửi; backend chỉ nhận đồng bộ qua /auth/verify-email-sync
(X-Internal-Secret, gọi từ server Next sau khi Supabase xác nhận email).
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.api.security import INTERNAL_SECRET_HEADER
from backend.config import get_settings
from backend.db.base import SessionLocal, engine
from backend.db.models import Account, Patient
from backend.main import app


def _db_ok() -> bool:
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_ok(), reason="Cần Postgres thật")


@pytest.mark.asyncio
async def test_dang_ky_chua_xac_minh_khong_dung_duoc_token_cho_toi_khi_xac_minh():
    email = f"verify-gate-{uuid.uuid4().hex[:8]}@example.com"
    pw = "mat-khau-test-123"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        try:
            r = await c.post("/api/v1/auth/register", json={"full_name": "T", "email": email, "password": pw})
            assert r.status_code == 201
            token = r.json()["access_token"]
            # Tài khoản lưu Postgres, chưa xác minh
            db = SessionLocal()
            acc = db.query(Account).filter(Account.email == email).one()
            assert acc.is_email_verified is False
            db.close()

            assert (await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 403
            assert (await c.post("/api/v1/auth/login", json={"email": email, "password": pw})).status_code == 403
            # Đăng ký trùng (khác hoa/thường) -> 409, không tạo tài khoản thứ 2
            dup = await c.post("/api/v1/auth/register", json={"full_name": "T", "email": email.upper(), "password": pw})
            assert dup.status_code == 409

            # verify-email-sync KHÔNG có internal secret -> bị chặn (không bypass)
            assert (await c.post("/api/v1/auth/verify-email-sync", json={"email": email})).status_code in (401, 403)
            ok = await c.post("/api/v1/auth/verify-email-sync", json={"email": email},
                              headers={INTERNAL_SECRET_HEADER: get_settings().internal_auth_secret})
            assert ok.status_code == 200

            db = SessionLocal()
            assert db.query(Account).filter(Account.email == email).one().is_email_verified is True
            assert db.query(Account).filter(Account.email.ilike(email)).count() == 1
            db.close()
            login = await c.post("/api/v1/auth/login", json={"email": email, "password": pw})
            assert login.status_code == 200
            me = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
            assert me.status_code == 200
        finally:
            db = SessionLocal()
            acc = db.query(Account).filter(Account.email.ilike(email)).first()
            if acc is not None:
                if acc.patient_id:
                    db.query(Patient).filter(Patient.id == acc.patient_id).delete(synchronize_session=False)
                db.delete(acc)
            db.commit()
            db.close()
