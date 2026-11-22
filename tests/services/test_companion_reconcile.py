"""TASK-CAPY-18: job doi soat Capybara Companion tren Postgres that.

Moi test chi bat companion cho benh nhan cua chinh no (allowlist) de job khong
dung vao du lieu khac trong DB test. Tu skip khi khong co DB.
"""

import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import (  # noqa: E402
    Account,
    CaregiverLink,
    Companion,
    CompanionCareDay,
    DoseEvent,
    Patient,
    PatientRewardAccount,
    PatientRewardEvent,
    SystemAuditLog,
)
from backend.services.auth import create_access_token  # noqa: E402
from backend.services.companion import service  # noqa: E402
from backend.services.reward_ledger import ngay_vn  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")

_VN = timedelta(hours=7)
HOM_NAY = ngay_vn(datetime.now(UTC))


def _luc(ngay: date, gio: int) -> datetime:
    return datetime(ngay.year, ngay.month, ngay.day, gio, 0, tzinfo=UTC) - _VN


@pytest.fixture
def benh_nhan(monkeypatch):
    """Tra ve ham tao benh nhan; tat ca deu duoc them vao allowlist va don sach."""
    tao: list[str] = []
    s = get_settings()
    monkeypatch.setattr(s, "companion_enabled", True)
    monkeypatch.setattr(s, "companion_rollout_percentage", 0)
    monkeypatch.setattr(s, "dose_runtime_mode", "legacy")
    monkeypatch.setattr(s, "companion_reconcile_lookback_days", 2)

    def _tao() -> str:
        pid = f"capy-rec-{uuid.uuid4().hex[:8]}"
        tao.append(pid)
        monkeypatch.setattr(s, "companion_allowlist", ",".join(tao))
        return pid

    yield _tao
    db = SessionLocal()
    try:
        for pid in tao:
            ids = [r.id for r in db.query(DoseEvent.id).filter(DoseEvent.patient_id == pid)]
            if ids:
                db.query(SystemAuditLog).filter(SystemAuditLog.target.in_(ids)).delete(synchronize_session=False)
            for m in (CompanionCareDay, Companion, PatientRewardEvent, PatientRewardAccount, DoseEvent, CaregiverLink):
                db.query(m).filter(m.patient_id == pid).delete(synchronize_session=False)
            db.query(Patient).filter(Patient.id == pid).delete(synchronize_session=False)
            db.query(Account).filter(Account.id.like(f"{pid}-%")).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _lieu(pid: str, ngay: date, gio: int, status: str = "PENDING", bao_cao: datetime | None = None) -> str:
    hen = _luc(ngay, gio)
    db = SessionLocal()
    try:
        d = DoseEvent(prescription_id="presc-capy-rec", patient_id=pid, scheduled_at=hen,
                      window_start=hen - timedelta(minutes=30), window_end=hen + timedelta(minutes=30),
                      status=status, expected_items=[], first_reported_at=bao_cao)
        db.add(d)
        db.commit()
        return d.id
    finally:
        db.close()


def _units(pid: str, ngay: date) -> int | None:
    db = SessionLocal()
    try:
        row = db.get(CompanionCareDay, (pid, ngay))
        return row.units if row else None
    finally:
        db.close()


def _job() -> service.ThongKeDoiSoat:
    return service.doi_soat_gan_day(SessionLocal)


def test_phuc_hoi_khi_hook_bo_lo_va_chay_lai_khong_doi_gi(benh_nhan):
    pid = benh_nhan()
    # Lieu da xac nhan (first_reported_at da ghi) nhung khong co dong tien do -> hook da bo lo.
    _lieu(pid, HOM_NAY, 8, "TAKEN", bao_cao=_luc(HOM_NAY, 8) + timedelta(minutes=5))
    tk1 = _job()
    assert _units(pid, HOM_NAY) == 100
    assert tk1.recovered_missing == 1 and tk1.errors == 0
    tk2 = _job()
    assert (tk2.recovered_missing, tk2.schedule_adjusted, tk2.errors) == (0, 0, 0)
    assert _units(pid, HOM_NAY) == 100


def test_huy_lieu_giua_ngay_duoc_sua(benh_nhan):
    pid = benh_nhan()
    _lieu(pid, HOM_NAY, 8, "TAKEN", bao_cao=_luc(HOM_NAY, 8) + timedelta(minutes=5))
    toi = _lieu(pid, HOM_NAY, 20)
    db = SessionLocal()
    service.tinh_lai_ngay(db, patient_id=pid, ngay=HOM_NAY)
    db.commit()
    db.get(DoseEvent, toi).status = "CANCELLED"
    db.commit()
    db.close()
    assert _units(pid, HOM_NAY) == 50
    tk = _job()
    assert _units(pid, HOM_NAY) == 100 and tk.schedule_adjusted == 1 and tk.recovered_missing == 0


@pytest.mark.parametrize(("co", "mode", "ly_do"), [(False, "legacy", "FEATURE_OFF"), (True, "v2", "RUNTIME_UNSUPPORTED")])
def test_tat_hoac_v2_thi_khong_lam_gi(benh_nhan, monkeypatch, co, mode, ly_do):
    pid = benh_nhan()
    _lieu(pid, HOM_NAY, 8, "TAKEN", bao_cao=_luc(HOM_NAY, 8))
    monkeypatch.setattr(get_settings(), "companion_enabled", co)
    monkeypatch.setattr(get_settings(), "dose_runtime_mode", mode)
    tk = _job()
    assert tk.skipped_reason == ly_do and tk.patients == 0 and _units(pid, HOM_NAY) is None


def test_khong_quet_toan_bo_lich_su(benh_nhan):
    """Bao cao dung ngay nhung tu 3 ngay truoc, khong co vet PATCH gan day ->
    nam ngoai cua so; job khong dung toi (gioi han backfill khi bat co)."""
    pid = benh_nhan()
    cu = HOM_NAY - timedelta(days=3)
    _lieu(pid, cu, 8, "TAKEN", bao_cao=_luc(cu, 8))
    _job()
    assert _units(pid, cu) is None


def test_loi_mot_benh_nhan_khong_chan_benh_nhan_khac(benh_nhan, monkeypatch):
    hong, tot = benh_nhan(), benh_nhan()
    for pid in (hong, tot):
        _lieu(pid, HOM_NAY, 8, "TAKEN", bao_cao=_luc(HOM_NAY, 8))
    goc = service.tinh_lai_ngay

    def chon_loi(db, *, patient_id, ngay):
        if patient_id == hong:
            raise RuntimeError("hong")
        return goc(db, patient_id=patient_id, ngay=ngay)

    monkeypatch.setattr(service, "tinh_lai_ngay", chon_loi)
    tk = _job()
    assert tk.errors == 1 and _units(tot, HOM_NAY) == 100 and _units(hong, HOM_NAY) is None


@pytest.mark.asyncio
async def test_nguoi_than_duyet_ngay_d_cong_5_hook_loi_job_van_phuc_hoi(client, benh_nhan, monkeypatch):
    """EDGE CASE: benh nhan gui anh ngay D -> AWAITING (first_reported_at = D).
    Nguoi than duyet TAKEN ngay D+5, hook companion LOI. Ngay D nam NGOAI cua so
    "hom qua + hom nay" - job chi tim ra no nho vet audit DOSE_STATUS_CHANGE."""
    pid = benh_nhan()
    d = HOM_NAY - timedelta(days=5)
    dose = _lieu(pid, d, 21, "AWAITING_CAREGIVER", bao_cao=_luc(d, 21) + timedelta(minutes=10))
    cg = f"{pid}-cg"
    db = SessionLocal()
    db.add(Account(id=cg, full_name="NT", email=f"{cg}@example.local", password_hash="x", role="caregiver", status="active"))
    db.add(Patient(id=pid, full_name="BN reconcile"))
    db.add(CaregiverLink(caregiver_account_id=cg, patient_id=pid, relationship="con", status="accepted"))
    db.commit()
    db.close()

    with monkeypatch.context() as m:
        def hong(*_a, **_kw):
            raise RuntimeError("hook hong")

        m.setattr(service, "tinh_lai_ngay", hong)
        r = await client.patch(
            f"/api/v1/doses/{dose}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {create_access_token(sub=cg, role='caregiver')}"},
        )
    assert r.status_code == 200
    assert _units(pid, d) is None, "hook loi -> chua co tien do"

    tk = _job()
    assert _units(pid, d) == 100, "phuc hoi cho dung ngay D (ngay benh nhan bao cao)"
    assert tk.recovered_missing == 1


# --- CLI doi soat khoang ngay (scripts/companion_reconcile.py, TASK-CAPY-26) ---


def test_cli_dry_run_khong_ghi_apply_moi_ghi_va_idempotent(benh_nhan):
    """Bu cho truong hop scheduler ngung lau hon lookback: lieu 6 ngay truoc."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "companion_reconcile", Path(__file__).resolve().parents[2] / "scripts" / "companion_reconcile.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    pid = benh_nhan()
    cu = HOM_NAY - timedelta(days=6)
    _lieu(pid, cu, 8, "TAKEN", bao_cao=_luc(cu, 8))
    _job()
    assert _units(pid, cu) is None, "job thuong khong nhin lai 6 ngay"

    kho = cli.chay(SessionLocal, tu=cu, den=HOM_NAY, patient_id=pid)
    assert [c["care_date"] for c in kho["changed"]] == [cu.isoformat()] and _units(pid, cu) is None, "dry-run khong ghi"
    cli.chay(SessionLocal, tu=cu, den=HOM_NAY, patient_id=pid, apply=True)
    assert _units(pid, cu) == 100
    assert cli.chay(SessionLocal, tu=cu, den=HOM_NAY, patient_id=pid, apply=True)["changed"] == []
    with pytest.raises(ValueError):
        cli.chay(SessionLocal, tu=HOM_NAY - timedelta(days=40), den=HOM_NAY)


def test_job_tim_ra_ngay_cua_xac_nhan_lai_lieu_fallback(benh_nhan):
    """Xac nhan lai lieu fallback (DOSE_EXPLICIT_CONFIRM) khong doi status hay
    first_reported_at - neu hook companion loi, job chi tim ra ngay do qua vet
    audit nay (review PR #11, 2026-11-14)."""
    from backend.services.scheduling.slot_summary import cap_benh_nhan_ngay_doi_trang_thai_tu

    pid = benh_nhan()
    ngay_cu = HOM_NAY - timedelta(days=4)
    dose = _lieu(pid, ngay_cu, 8, "TAKEN", bao_cao=_luc(ngay_cu, 9))
    db = SessionLocal()
    try:
        db.add(SystemAuditLog(actor_id=f"{pid}-acc", actor_name="t", actor_role="patient",
                              action=f"DOSE_EXPLICIT_CONFIRM dose={dose}", target=dose))
        db.commit()
        cap = cap_benh_nhan_ngay_doi_trang_thai_tu(db, moc=datetime.now(UTC) - timedelta(hours=1))
    finally:
        db.close()
    assert (pid, ngay_cu) in cap
