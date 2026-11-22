import os
from unittest.mock import AsyncMock

# B2: route-level tests build the real Agent V2 wiring from settings; without
# these the semantic safety classifier and the web search fallback would make
# a live OpenAI call whenever a real key is present in .env. Set before any
# backend import so the cached settings see it. Tests of either inject fakes.
os.environ.setdefault("AGENT_SEMANTIC_SAFETY_ENABLED", "false")
os.environ.setdefault("AGENT_WEB_SEARCH_ENABLED", "false")
os.environ.setdefault("AGENT_DRUG_PREFETCH_ENABLED", "false")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from backend.api.security import INTERNAL_SECRET_HEADER  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402

# TASK-010: JWT cua fixture `client` dung role=caregiver (KHONG phai
# patient) - vi get_current_patient_id() (backend/api/security.py) chi tin
# request.patient_id trong body cho role != patient (patient bi khoa vao
# patient_id cua chinh JWT). Cac test hien co (test_chat_routes.py,
# test_rate_limit.py, test_drug_confirmation_e2e.py...) deu tu sinh
# patient_id ngau nhien MOI test roi truyen qua body - can role duoc phep
# "goi ho benh nhan" de khong phai vi lai toan bo bo test nay (mint 1
# Account that/JWT rieng cho tung patient_id ngau nhien) trong pham vi
# TASK-010. Test rieng cho hanh vi role=patient xem test_get_current_patient_id.py.
_TEST_CALLER_ID = "test-caregiver-conftest"


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing API endpoints. Gui san:
    - `X-Internal-Secret` (rao tam CON LAI cho escalation_routes.py - chua
      thuoc pham vi TASK-010, xem tasks/TASK-010-auth-api.md muc "Ghi chu").
    - `Authorization: Bearer <JWT>` (role=caregiver, TASK-010) cho
      /api/v1/chat va cac route dung get_current_user.
    Test nao can mo phong nguoi goi khac (role khac, thieu token...) tu tao
    client rieng (xem test_chat_security_gate.py)."""
    transport = ASGITransport(app=app)
    settings = get_settings()
    token = create_access_token(sub=_TEST_CALLER_ID, role="caregiver")
    headers = {
        INTERNAL_SECRET_HEADER: settings.internal_auth_secret,
        "Authorization": f"Bearer {token}",
    }
    db = SessionLocal()
    try:
        db.add(
            Account(
                id=_TEST_CALLER_ID,
                full_name="Test caregiver caller",
                email="test-caregiver-conftest@example.local",
                password_hash="not-a-real-hash",
                role="caregiver",
                status="active",
            )
        )
        db.commit()
        async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
            yield ac
    finally:
        db.query(Account).filter(Account.id == _TEST_CALLER_ID).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests.

    Usage in test:
        def test_something(mock_llm):
            # LLM calls will return mock response instead of hitting OpenAI
            ...
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock
