"""Cơ chế an toàn của scripts/seed_hackathon_demo.py — chỉ chạy DB local được cho phép."""

import importlib.util
from pathlib import Path

import pytest

from backend.config import get_settings

_spec = importlib.util.spec_from_file_location(
    "seed_hackathon_demo", Path(__file__).resolve().parent.parent / "scripts" / "seed_hackathon_demo.py"
)
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


@pytest.fixture
def env(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "app_env", "development")
    monkeypatch.setenv("CAPYMEDI_DEMO_PASSWORD", "mat-khau-demo-du-dai")
    monkeypatch.delenv("CAPYMEDI_DEMO_ALLOWED_DBS", raising=False)
    return monkeypatch, s


@pytest.mark.parametrize(
    "url,ly_do",
    [
        ("postgresql://u:p@db.prod.example.com:5432/capytest", "local"),
        ("postgresql://u:p@localhost:5432/vmec04", "CAPYMEDI_DEMO_ALLOWED_DBS"),
        ("postgresql://u:p@localhost:5432/", "thieu"),
    ],
)
def test_tu_choi_db_khong_duoc_phep(env, url, ly_do):
    mp, s = env
    mp.setattr(s, "database_url", url)
    with pytest.raises(SystemExit, match=ly_do):
        seed.kiem_tra_moi_truong()


def test_tu_choi_production_va_thieu_mat_khau(env):
    mp, s = env
    mp.setattr(s, "database_url", "postgresql://u:p@127.0.0.1:55432/capytest")
    mp.setattr(s, "app_env", "production")
    with pytest.raises(SystemExit, match="production"):
        seed.kiem_tra_moi_truong()
    mp.setattr(s, "app_env", "development")
    mp.setenv("CAPYMEDI_DEMO_PASSWORD", "ngan")
    with pytest.raises(SystemExit, match="CAPYMEDI_DEMO_PASSWORD"):
        seed.kiem_tra_moi_truong()


def test_cho_phep_db_local_trong_allowlist(env):
    mp, s = env
    mp.setattr(s, "database_url", "postgresql://u:p@127.0.0.1:55432/capytest")
    assert seed.kiem_tra_moi_truong() == "mat-khau-demo-du-dai"


def test_moi_dinh_danh_demo_co_tien_to():
    ids = [seed.pid(1), seed.acc_bn(2), seed.acc_bs(3), seed.doctor_id(1), seed.email_bn(1), seed.email_bs(3)]
    assert all(x.startswith(seed.PREFIX) for x in ids)
    assert all(e.endswith("@example.com") for e in (seed.email_bn(1), seed.email_bs(2)))
