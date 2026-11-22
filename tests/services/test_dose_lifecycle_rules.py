"""TASK-CAPY-04/07: quy tac PATCH lieu va first_reported_at - ham thuan,
khong can DB. Xem specs/business-rules.md muc 8 (ADR-0016)."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.db.models import DoseEvent
from backend.services.dose_lifecycle import (
    LATE_REPORT_DAYS,
    LY_DO_KHONG_CHO_DAT,
    LY_DO_QUA_HAN,
    danh_dau_da_bao_cao,
    kiem_tra_cap_nhat_lieu,
)

NOW = datetime(2026, 11, 14, 3, 0, tzinfo=UTC)  # 10:00 gio VN


def _kt(current, target, *, role="patient", owner=True, lui=timedelta(0), khoang=True):
    hen = NOW - lui
    return kiem_tra_cap_nhat_lieu(
        current_status=current,
        target_status=target,
        actor_role=role,
        is_owner=owner,
        scheduled_at=hen,
        window_end=hen + timedelta(minutes=30),
        now=NOW,
        ap_dung_khoang_bao_cao=khoang,
    )


@pytest.mark.parametrize(
    ("current", "target", "ky_vong"),
    [
        ("PENDING", "TAKEN", "TAKEN"),
        ("PENDING", "MISSED", "MISSED"),
        ("MISSED", "TAKEN", "TAKEN"),
        ("TAKEN", "MISSED", "MISSED"),
    ],
)
def test_chuyen_hop_le(current, target, ky_vong):
    qd = _kt(current, target)
    assert qd.hanh_dong == "CHO_PHEP" and qd.trang_thai_moi == ky_vong


@pytest.mark.parametrize("target", ["CANCELLED", "PENDING", "DELAYED", "AWAITING_CAREGIVER"])
def test_status_ngoai_whitelist_bi_tu_choi(target):
    qd = _kt("PENDING", target)
    assert qd.hanh_dong == "TU_CHOI" and qd.ly_do == LY_DO_KHONG_CHO_DAT


def test_gui_lai_da_uong_la_no_op_ke_ca_delayed():
    assert _kt("TAKEN", "TAKEN").hanh_dong == "NO_OP"
    assert _kt("DELAYED", "TAKEN").hanh_dong == "NO_OP"
    assert _kt("MISSED", "MISSED").hanh_dong == "NO_OP"


def test_khong_mo_lai_lieu_da_huy():
    assert _kt("CANCELLED", "TAKEN").hanh_dong == "TU_CHOI"


def test_awaiting_chi_nguoi_khac_duyet_va_khong_gioi_han_ngay():
    assert _kt("AWAITING_CAREGIVER", "TAKEN", owner=True).hanh_dong == "TU_CHOI"
    qd = _kt("AWAITING_CAREGIVER", "TAKEN", role="caregiver", owner=False, lui=timedelta(days=30))
    assert qd.hanh_dong == "CHO_PHEP"


def test_khoang_bao_cao_tre():
    trong = _kt("MISSED", "TAKEN", lui=timedelta(days=LATE_REPORT_DAYS))
    assert trong.hanh_dong == "CHO_PHEP" and trong.trang_thai_moi == "DELAYED"
    ngoai = _kt("MISSED", "TAKEN", lui=timedelta(days=LATE_REPORT_DAYS + 1))
    assert ngoai.hanh_dong == "TU_CHOI" and ngoai.ly_do == LY_DO_QUA_HAN
    # Bac si khong bi gioi han; co tat (mac dinh production) cung khong gioi han.
    assert _kt("MISSED", "TAKEN", role="doctor", owner=False, lui=timedelta(days=30)).hanh_dong == "CHO_PHEP"
    assert _kt("MISSED", "TAKEN", lui=timedelta(days=30), khoang=False).hanh_dong == "CHO_PHEP"


def test_first_reported_at_ghi_dung_mot_lan():
    dose = DoseEvent(status="TAKEN", scheduled_at=NOW, first_reported_at=None)
    assert danh_dau_da_bao_cao(dose, NOW) is True
    dose.status = "MISSED"
    assert danh_dau_da_bao_cao(dose, NOW + timedelta(hours=1)) is False
    dose.status = "TAKEN"
    assert danh_dau_da_bao_cao(dose, NOW + timedelta(hours=2)) is False
    assert dose.first_reported_at == NOW


def test_first_reported_at_khong_ghi_cho_missed_nhung_ghi_cho_awaiting():
    missed = DoseEvent(status="MISSED", scheduled_at=NOW, first_reported_at=None)
    assert danh_dau_da_bao_cao(missed, NOW) is False and missed.first_reported_at is None
    awaiting = DoseEvent(status="AWAITING_CAREGIVER", scheduled_at=NOW, first_reported_at=None)
    assert danh_dau_da_bao_cao(awaiting, NOW) is True
