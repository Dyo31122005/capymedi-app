"""Thuat toan "Ngay cham soc" - HAM THUAN, khong cham DB (TASK-CAPY-12, ADR-0016,
specs/business-rules.md BR-8.9/8.10).

Moi ngay toi da DAY_UNITS don vi noi bo: floor(DAY_UNITS * k / n), voi
  n = so slot khong CANCELLED co ngay hen = ngay do,
  k = so slot dang TAKEN/DELAYED VA bao cao "da uong" LAN DAU trong chinh ngay hen
      VA khong phai "chi fallback anh" (QA-03).
AWAITING_CAREGIVER chua duoc tinh (cho nguoi than duyet TAKEN). Don vi noi bo
KHONG BAO GIO hien cho nguoi dung - chi ten giai doan va %.
Moi hang so la gia thuyet san pham, cau hinh duoc - cho PO duyet (D-5).
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.services.scheduling.slot_summary import SlotFact

DAY_UNITS = 100
# Nguong growth_units cho giai doan 1..4 (= 0 / 3 / 14 / 42 ngay cham soc tron).
STAGE_THRESHOLDS: tuple[int, ...] = (0, 300, 1400, 4200)
STAGE_KEYS: tuple[str, ...] = ("CAPY_SO_SINH", "CAPY_CON", "CAPY_NHO", "CAPY_Y_TA")
STAGE_LABELS: tuple[str, ...] = ("Capy sơ sinh", "Capy con", "Capy nhỡ", "Capy y tá")
MAX_STAGE = len(STAGE_THRESHOLDS)

_TRANG_THAI_LON_LEN = frozenset({"TAKEN", "DELAYED"})


def eligible(fact: SlotFact) -> bool:
    """Slot tinh vao mau so: moi slot con ton tai, tru CANCELLED (bac si dung)."""
    return fact.status != "CANCELLED"


def growth_done(fact: SlotFact) -> bool:
    """Slot tinh vao tu so. Bao cao khac ngay hen (bao cao tre) KHONG tinh -
    ho so lam sang van ghi, chi Capy khong lon (BR-8.9)."""
    return (
        fact.status in _TRANG_THAI_LON_LEN
        and fact.ngay_bao_cao is not None
        and fact.ngay_bao_cao == fact.ngay_hen
        # QA-03: anh sai het luot (khong co nguoi than) KHONG phai bang chung da
        # uong - ho so lam sang van TAKEN (chinh sach hien co), Capy chi lon khi
        # co xac nhan ro rang (tu khai / nguoi than duyet / anh khop).
        and not fact.chi_fallback_anh
    )


def dem_ngay(facts: Iterable[SlotFact]) -> tuple[int, int]:
    """(n, k) cua mot ngay."""
    facts = list(facts)
    return sum(1 for f in facts if eligible(f)), sum(1 for f in facts if growth_done(f))


def day_units(k: int, n: int) -> int:
    """floor(DAY_UNITS*k/n), tran DAY_UNITS. n == 0 (ngay khong co lieu) -> 0."""
    if n <= 0:
        return 0
    return (DAY_UNITS * min(k, n)) // n


def stage_for(growth_units: int) -> int:
    """Giai doan 1..MAX_STAGE (bac cao nhat co growth >= nguong)."""
    stage = 1
    for i, nguong in enumerate(STAGE_THRESHOLDS):
        if growth_units >= nguong:
            stage = i + 1
    return stage


def progress_pct(growth_units: int) -> int:
    """% den giai doan ke tiep (0..99). Giai doan cuoi -> 100."""
    stage = stage_for(growth_units)
    if stage >= MAX_STAGE:
        return 100
    dau, cuoi = STAGE_THRESHOLDS[stage - 1], STAGE_THRESHOLDS[stage]
    return (100 * (growth_units - dau)) // (cuoi - dau)
