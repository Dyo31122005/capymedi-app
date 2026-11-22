"""TASK-CAPY-12: thuat toan "Ngay cham soc" - ham thuan (ADR-0016, BR-8.9)."""

from datetime import date, timedelta

import pytest

from backend.services.companion import progression as p
from backend.services.scheduling.slot_summary import SlotFact

D = date(2026, 11, 10)


def _f(status: str, bao_cao: date | None = D) -> SlotFact:
    return SlotFact(status=status, ngay_hen=D, ngay_bao_cao=bao_cao)


@pytest.mark.parametrize(
    ("fact", "eligible", "done"),
    [
        (_f("TAKEN"), True, True),
        (_f("DELAYED"), True, True),
        (_f("TAKEN", D + timedelta(days=1)), True, False),  # bao cao tre: ghi ho so, khong lon
        (_f("TAKEN", None), True, False),  # du lieu cu chua co first_reported_at
        (_f("AWAITING_CAREGIVER"), True, False),  # cho nguoi than duyet
        (_f("MISSED", None), True, False),
        (_f("PENDING", None), True, False),
        (_f("CANCELLED", None), False, False),
    ],
)
def test_eligible_va_growth_done(fact, eligible, done):
    assert p.eligible(fact) is eligible
    assert p.growth_done(fact) is done


def test_day_units_tran_va_floor():
    assert p.day_units(0, 0) == 0
    assert p.day_units(1, 1) == 100
    assert p.day_units(1, 4) == 25
    assert p.day_units(2, 3) == 66
    assert p.day_units(5, 4) == 100  # k > n khong vuot tran


@pytest.mark.parametrize(
    ("growth", "stage", "pct"),
    [(0, 1, 0), (299, 1, 99), (300, 2, 0), (1399, 2, 99), (1400, 3, 0), (4199, 3, 99), (4200, 4, 100)],
)
def test_bien_nguong(growth, stage, pct):
    assert p.stage_for(growth) == stage
    assert p.progress_pct(growth) == pct


def _ngay_toi_giai_doan(units_moi_ngay: int, stage: int) -> int:
    nguong, tong, ngay = p.STAGE_THRESHOLDS[stage - 1], 0, 0
    while tong < nguong:
        tong += units_moi_ngay
        ngay += 1
    return ngay


@pytest.mark.parametrize(
    ("k", "n", "ky_vong"),
    [
        (1, 1, (3, 14, 42)),  # §4.5 hang 1: 1 lieu/ngay 100%
        (4, 4, (3, 14, 42)),  # hang 2: 4 lieu/ngay 100% - KHONG lon nhanh hon
        (3, 4, (4, 19, 56)),  # hang 2b
        (2, 3, (5, 22, 64)),  # hang 2c
    ],
)
def test_cong_bang_theo_tan_suat(k, n, ky_vong):
    u = p.day_units(k, n)
    assert tuple(_ngay_toi_giai_doan(u, s) for s in (2, 3, 4)) == ky_vong


def test_dot_ngan_3_ngay_va_bo_1_lieu():
    assert p.stage_for(3 * p.day_units(1, 1)) == 2  # hang 4a
    assert p.progress_pct(2 * p.day_units(1, 1)) == 66  # hang 4b
