"""TASK-024 (api-contracts.md §1c-5) - nut "Tham quan": GET/POST
/api/v1/auth/guest-login va chan doi mat khau tai khoan khach. Dung DB that
(giong test_auth_routes.py) - tao/xoa tai khoan rieng moi test, khong mock ORM."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Account, DoctorWatch, Patient  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.auth import decode_token, hash_password  # noqa: E402

PASSWORD = "a-real-test-password-123"


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def guest_accounts():
    """1 bac si + 1 benh nhan, email ngau nhien de khong dung du lieu khac."""
    suffix = uuid.uuid4().hex[:8]
    patient_id = f"test-guest-patient-{suffix}"
    doctor = Account(
        full_name="Bác sĩ Khách Test",
        email=f"test-guest-doctor-{suffix}@example.com",
        password_hash=hash_password(PASSWORD),
        role="doctor",
        doctor_id=f"test-guest-doc-{suffix}",
    )
    patient = Account(
        full_name="Bệnh nhân Khách Test",
        email=f"test-guest-patient-{suffix}@example.com",
        password_hash=hash_password(PASSWORD),
        role="patient",
        patient_id=patient_id,
    )
    db = SessionLocal()
    db.add(Patient(id=patient_id, full_name=patient.full_name))
    db.add_all([doctor, patient])
    db.commit()
    ids = {"doctor": doctor.id, "patient": patient.id}
    emails = {"doctor": doctor.email, "patient": patient.email}
    db.close()

    yield {"ids": ids, "emails": emails, "patient_id": patient_id}

    db = SessionLocal()
    db.query(DoctorWatch).filter(DoctorWatch.patient_id == patient_id).delete(synchronize_session=False)
    db.query(Account).filter(Account.id.in_(list(ids.values()))).delete(synchronize_session=False)
    db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.fixture
def guest_config(monkeypatch):
    """Dat bien moi truong roi xoa cache Settings; tu khoi phuc sau test."""

    def _apply(*, enabled: bool, doctor_email: str = "", patient_email: str = "") -> None:
        monkeypatch.setenv("GUEST_LOGIN_ENABLED", "true" if enabled else "false")
        monkeypatch.setenv("GUEST_DOCTOR_EMAIL", doctor_email)
        monkeypatch.setenv("GUEST_PATIENT_EMAIL", patient_email)
        get_settings.cache_clear()

    yield _apply
    get_settings.cache_clear()


def _set_status(account_id: str, value: str) -> None:
    db = SessionLocal()
    db.query(Account).filter(Account.id == account_id).update({"status": value})
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_disabled_by_default_hides_buttons_and_refuses_login(client, guest_accounts, guest_config):
    guest_config(
        enabled=False,
        doctor_email=guest_accounts["emails"]["doctor"],
        patient_email=guest_accounts["emails"]["patient"],
    )
    status = await client.get("/api/v1/auth/guest-login")
    assert status.status_code == 200
    assert status.json() == {"enabled": False, "roles": []}

    for role in ("doctor", "patient"):
        response = await client.post("/api/v1/auth/guest-login", json={"role": role})
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_enabled_issues_session_for_each_role_with_login_shape(client, guest_accounts, guest_config):
    guest_config(
        enabled=True,
        doctor_email=guest_accounts["emails"]["doctor"],
        patient_email=guest_accounts["emails"]["patient"],
    )
    status = await client.get("/api/v1/auth/guest-login")
    assert status.json() == {"enabled": True, "roles": ["doctor", "patient"]}

    for role in ("doctor", "patient"):
        response = await client.post("/api/v1/auth/guest-login", json={"role": role})
        assert response.status_code == 200, response.text
        body = response.json()
        # Cung shape voi POST /auth/login - frontend dung chung xu ly phien.
        assert set(body) >= {"access_token", "token_type", "expires_in", "refresh_token", "user"}
        assert body["user"]["id"] == guest_accounts["ids"][role]
        assert body["user"]["role"] == role
        payload = decode_token(body["access_token"])
        assert payload["sub"] == guest_accounts["ids"][role]
        assert payload["role"] == role

        me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
        assert me.status_code == 200
        assert me.json()["role"] == role


@pytest.mark.asyncio
async def test_configured_email_matches_case_insensitively(client, guest_accounts, guest_config):
    guest_config(enabled=True, doctor_email="  " + guest_accounts["emails"]["doctor"].upper() + " ")
    response = await client.post("/api/v1/auth/guest-login", json={"role": "doctor"})
    assert response.status_code == 200
    assert response.json()["user"]["id"] == guest_accounts["ids"]["doctor"]


@pytest.mark.asyncio
async def test_unconfigured_role_is_not_offered(client, guest_accounts, guest_config):
    guest_config(enabled=True, doctor_email=guest_accounts["emails"]["doctor"])
    status = await client.get("/api/v1/auth/guest-login")
    assert status.json() == {"enabled": True, "roles": ["doctor"]}
    response = await client.post("/api/v1/auth/guest-login", json={"role": "patient"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_email_pointing_at_wrong_role_fails_closed(client, guest_accounts, guest_config):
    """Cau hinh nham email benh nhan vao o bac si: KHONG duoc cap phien bac si,
    cung KHONG duoc cap phien benh nhan qua nut bac si."""
    guest_config(enabled=True, doctor_email=guest_accounts["emails"]["patient"])
    status = await client.get("/api/v1/auth/guest-login")
    assert status.json() == {"enabled": False, "roles": []}
    response = await client.post("/api/v1/auth/guest-login", json={"role": "doctor"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_locked_guest_account_fails_closed(client, guest_accounts, guest_config):
    guest_config(
        enabled=True,
        doctor_email=guest_accounts["emails"]["doctor"],
        patient_email=guest_accounts["emails"]["patient"],
    )
    _set_status(guest_accounts["ids"]["doctor"], "locked")
    status = await client.get("/api/v1/auth/guest-login")
    assert status.json() == {"enabled": True, "roles": ["patient"]}
    response = await client.post("/api/v1/auth/guest-login", json={"role": "doctor"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unknown_email_fails_closed(client, guest_accounts, guest_config):
    guest_config(enabled=True, doctor_email=f"khong-ton-tai-{uuid.uuid4().hex[:8]}@example.com")
    response = await client.post("/api/v1/auth/guest-login", json={"role": "doctor"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_role_outside_doctor_patient_is_rejected(client, guest_config):
    guest_config(enabled=True)
    for role in ("admin", "super_admin", "caregiver", ""):
        response = await client.post("/api/v1/auth/guest-login", json={"role": role})
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_guest_account_cannot_change_password(client, guest_accounts, guest_config):
    guest_config(enabled=True, patient_email=guest_accounts["emails"]["patient"])
    login = await client.post("/api/v1/auth/guest-login", json={"role": "patient"})
    token = login.json()["access_token"]
    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "mat-khau-moi-123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    # Mat khau cu van dang nhap tay duoc - thao tac bi chan hoan toan, khong doi nua chung.
    manual = await client.post(
        "/api/v1/auth/login", json={"email": guest_accounts["emails"]["patient"], "password": PASSWORD}
    )
    assert manual.status_code == 200


@pytest.mark.asyncio
async def test_guest_password_protection_holds_even_when_feature_disabled(client, guest_accounts, guest_config):
    guest_config(enabled=False, patient_email=guest_accounts["emails"]["patient"])
    login = await client.post(
        "/api/v1/auth/login", json={"email": guest_accounts["emails"]["patient"], "password": PASSWORD}
    )
    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "mat-khau-moi-123"},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 403
