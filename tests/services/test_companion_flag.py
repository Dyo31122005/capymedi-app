"""TASK-CAPY-16: co + cohort + runtime cua Capybara Companion (khong can DB)."""

import pytest

from backend.config import get_settings
from backend.services.companion import service


@pytest.fixture
def cfg(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "companion_enabled", True)
    monkeypatch.setattr(s, "companion_rollout_percentage", 0)
    monkeypatch.setattr(s, "companion_allowlist", "")
    monkeypatch.setattr(s, "dose_runtime_mode", "legacy")
    return s


def test_mac_dinh_tat():
    s = get_settings()
    assert s.companion_enabled is False and s.companion_rollout_percentage == 0 and s.companion_allowlist == ""


def test_co_tat_thi_feature_off(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "companion_enabled", False)
    monkeypatch.setattr(cfg, "companion_rollout_percentage", 100)
    assert service.ly_do_khong_kha_dung("p1") == "FEATURE_OFF"


def test_bat_co_nhung_ngoai_cohort_van_tat(cfg):
    assert service.companion_bat_cho("p1") is False


def test_allowlist(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "companion_allowlist", " p1 , p2 ")
    assert service.companion_bat_cho("p1") and service.companion_bat_cho("p2")
    assert not service.companion_bat_cho("p3")


def test_cohort_on_dinh_va_don_dieu(cfg, monkeypatch):
    ids = [f"bn-{i}" for i in range(400)]
    monkeypatch.setattr(cfg, "companion_rollout_percentage", 20)
    vao_20 = {i for i in ids if service.companion_bat_cho(i)}
    assert vao_20 == {i for i in ids if service.companion_bat_cho(i)}, "on dinh giua cac lan goi"
    assert 40 <= len(vao_20) <= 120
    monkeypatch.setattr(cfg, "companion_rollout_percentage", 50)
    assert vao_20 <= {i for i in ids if service.companion_bat_cho(i)}, "tang pct khong day ai ra"
    monkeypatch.setattr(cfg, "companion_rollout_percentage", 100)
    assert all(service.companion_bat_cho(i) for i in ids)


@pytest.mark.parametrize(("mode", "ky_vong"), [("legacy", None), ("shadow", None), ("v2", "RUNTIME_UNSUPPORTED")])
def test_runtime(cfg, monkeypatch, mode, ky_vong):
    monkeypatch.setattr(cfg, "companion_allowlist", "p1")
    monkeypatch.setattr(cfg, "dose_runtime_mode", mode)
    assert service.ly_do_khong_kha_dung("p1") == ky_vong
