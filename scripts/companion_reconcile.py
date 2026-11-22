#!/usr/bin/env python3
"""Doi soat tien do Capybara Companion cho mot KHOANG NGAY bat ky (TASK-CAPY-26).

BOI CANH: job `doi_soat_companion` (escalation_scheduler, moi 15 phut) chi nhin
lai `companion_reconcile_lookback_days` ngay (mac dinh 2). Neu scheduler ngung
chay lau hon the (container sap, deploy loi...), cac xac nhan trong khoang do
co the khong bao gio duoc tinh. Script nay la cong cu van hanh de bu lai: no
GOI LAI DUNG `companion.service.tinh_lai_ngay` (tat dinh, chi tang, idempotent)
cho tung (benh nhan, ngay) trong khoang - khong co logic tinh rieng.

AN TOAN:
  - MAC DINH DRY-RUN: tinh trong transaction roi ROLLBACK, in ra nhung gi SE doi.
    Phai truyen --apply moi ghi that.
  - Khoang toi da 31 ngay moi lan chay.
  - Chi dong vao bang companion/companion_care_day (khong sua dose_event, LP/SP).
  - Ton trong co + cohort + runtime giong job (companion_bat_cho); co tat thi khong lam gi.
  - Log/in ra chi co patient_id va ngay (khong PHI).

Usage:
    # xem truoc 7 ngay qua, KHONG ghi gi
    python scripts/companion_reconcile.py --from 2026-11-07 --to 2026-11-14

    # chay that cho 1 benh nhan
    python scripts/companion_reconcile.py --from 2026-11-07 --to 2026-11-14 --patient <id> --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import DoseEvent  # noqa: E402
from backend.services.companion import service  # noqa: E402
from backend.services.reward_ledger import ngay_vn  # noqa: E402

KHOANG_TOI_DA_NGAY = 31


def _benh_nhan_trong_khoang(db: Session, tu: date, den: date) -> set[str]:
    """Benh nhan co lieu hen trong [tu, den] (ngay VN) - loc rong +-1 ngay UTC roi chot bang ngay_vn."""
    dau = datetime.combine(tu - timedelta(days=1), datetime.min.time())
    cuoi = datetime.combine(den + timedelta(days=2), datetime.min.time())
    rows = db.execute(
        select(DoseEvent.patient_id, DoseEvent.scheduled_at).where(
            DoseEvent.scheduled_at >= dau, DoseEvent.scheduled_at < cuoi
        )
    ).all()
    return {pid for pid, hen in rows if tu <= ngay_vn(hen) <= den}


def chay(
    session_factory: Callable[[], Session],
    *,
    tu: date,
    den: date,
    patient_id: str | None = None,
    apply: bool = False,
) -> dict:
    if den < tu or (den - tu).days + 1 > KHOANG_TOI_DA_NGAY:
        raise ValueError(f"Khoang ngay khong hop le (toi da {KHOANG_TOI_DA_NGAY} ngay).")
    db = session_factory()
    try:
        ung_vien = {patient_id} if patient_id else _benh_nhan_trong_khoang(db, tu, den)
    finally:
        db.close()

    ket_qua = {"apply": apply, "from": tu.isoformat(), "to": den.isoformat(), "patients": 0, "changed": [], "skipped": []}
    for pid in sorted(ung_vien):
        if not service.companion_bat_cho(pid):
            ket_qua["skipped"].append(pid)
            continue
        ket_qua["patients"] += 1
        db = session_factory()
        try:
            ngay = tu
            while ngay <= den:
                kq = service.tinh_lai_ngay(db, patient_id=pid, ngay=ngay)
                if kq.units_sau != kq.units_truoc:
                    ket_qua["changed"].append(
                        {"patient_id": pid, "care_date": ngay.isoformat(), "units_before": kq.units_truoc,
                         "units_after": kq.units_sau}
                    )
                ngay += timedelta(days=1)
            if apply:
                db.commit()
            else:
                db.rollback()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    return ket_qua


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="tu", required=True, type=date.fromisoformat)
    ap.add_argument("--to", dest="den", required=True, type=date.fromisoformat)
    ap.add_argument("--patient", dest="patient_id")
    ap.add_argument("--apply", action="store_true", help="Ghi that (mac dinh chi dry-run).")
    args = ap.parse_args()
    print(json.dumps(chay(SessionLocal, tu=args.tu, den=args.den, patient_id=args.patient_id, apply=args.apply),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
