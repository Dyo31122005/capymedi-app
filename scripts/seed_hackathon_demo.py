#!/usr/bin/env python3
"""Du lieu DEMO hackathon: 3 benh nhan + 3 bac si - BAN GHI THAT trong PostgreSQL.

CHI CHAY LOCAL/TEST da cho phep RO RANG. Tu choi neu:
  - host DB khong phai localhost/127.0.0.1/::1/db, hoac khong doc duoc URL;
  - APP_ENV=production;
  - ten DB khong nam trong CAPYMEDI_DEMO_ALLOWED_DBS (mac dinh chi "capytest");
  - thieu CAPYMEDI_DEMO_PASSWORD (mat khau demo KHONG nam trong ma nguon -
    dat trong file env bi git ignore, vd `.env.local`, hoac export khi chay).

IDEMPOTENT: moi id/email/doctor_id cua demo deu bat dau bang `hackathon-demo`.
Moi lan chay xoa DUNG cac dong co tien to do (tren moi bang co cot dinh danh
benh nhan/tai khoan/bac si - doc tu information_schema) roi tao lai. Khong
TRUNCATE, khong dong vao ban ghi khong co tien to.

Luong tao du lieu (KHONG bom thang vao state FE):
  1. Tai khoan + ho so (insert DB, bcrypt that qua hash_password). Dang nhap
     cua CapyMedi xac thuc bang Account.password_hash (POST /auth/login) -
     Supabase chi dung de GUI EMAIL xac minh luc tu dang ky, nen khong can tao
     user Supabase va khong gui email nao.
  2. Moi bac si DANG NHAP that -> KE DON that -> DUYET that qua API; backend tu
     sinh dose_event.
  3. Lich su cac ngay TRUOC (du lieu hu cau, ghi ro trong report): dat trang
     thai lieu da qua roi tinh DIEM + CAPY bang chinh ham nghiep vu
     (reward_ledger.award_dose_on_time, companion.service.tinh_lai_ngay).

Kich ban:
  - BN1 (BS1): uong DUNG GIO 2 ngay qua; lieu hom nay theo gio nhac.
  - BN2 (BS2): lieu TRE (DELAYED) + BO LIEU (MISSED).
    (Khong seed don NHAP: FE da bo hang doi duyet - commit 52c301e, ke don va
    duyet la 1 hop thoai xac nhan tren /doctor/prescribe, ADR-0010.)
  - BN3 (BS3): XAC NHAN BANG ANH - lieu dang trong khung xac nhan luc seed.
  - Moi BS chi "Theo doi" (DoctorWatch) benh nhan cua minh -> kiem tra cach ly.

Che do:
    --auto              Docker Compose (service demo-seed) goi moi lan `up`: CHI chay khi
                        APP_ENV=demo VA ENABLE_DEMO_SEED=true; neu 6 tai khoan demo DA CO
                        thi BO QUA (khong reset lich su/diem/Capy da dung khi demo).
    --reset             Xoa + tao lai TOAN BO du lieu demo (chu dong goi; mac dinh khi
                        khong truyen co nao - tuong thich `make demo-seed`).
    --prepare-patient3  TRUOC GIO DEMO: dua 1 lieu PENDING cua BN3 vao khung xac nhan.

Usage (host): python scripts/seed_hackathon_demo.py --reset --api http://127.0.0.1:8001
Usage (Docker): docker compose run --rm demo-seed --prepare-patient3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from backend.api.dose_routes import _thuong_diem_neu_uong_du, _xac_dinh_ty_le_thuong  # noqa: E402
from backend.api.security import INTERNAL_SECRET_HEADER  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account, DoctorWatch, DoseEvent, Patient  # noqa: E402
from backend.services.auth import hash_password  # noqa: E402
from backend.services.companion import service as companion_service  # noqa: E402

PREFIX = "hackathon-demo"
HOST_LOCAL = frozenset({"localhost", "127.0.0.1", "::1", "db"})
VN = ZoneInfo("Asia/Ho_Chi_Minh")
# Cot dinh danh co the chua id demo - dung de don dep theo tien to.
COT_DINH_DANH = ("patient_id", "doctor_id", "account_id", "actor_id", "caregiver_account_id")

DOCTORS = [
    {"n": 1, "name": "BS. Trần Minh Anh (DEMO)"},
    {"n": 2, "name": "BS. Lê Quốc Huy (DEMO)"},
    {"n": 3, "name": "BS. Phạm Thu Hà (DEMO)"},
]
PATIENTS = [
    {"n": 1, "name": "Bà Nguyễn Thị Lan (DEMO)", "dob": date(1952, 4, 3), "gender": "nu", "kb": "dung_gio"},
    {"n": 2, "name": "Ông Trần Văn Hùng (DEMO)", "dob": date(1949, 9, 21), "gender": "nam", "kb": "tre_bo_lieu"},
    {"n": 3, "name": "Cô Lê Thị Mai (DEMO)", "dob": date(1963, 12, 8), "gender": "nu", "kb": "chup_anh"},
]


def pid(n: int) -> str:
    return f"{PREFIX}-patient-{n}"


def acc_bn(n: int) -> str:
    return f"{PREFIX}-patient-{n}-acct"


def acc_bs(n: int) -> str:
    return f"{PREFIX}-doctor-{n}-acct"


def doctor_id(n: int) -> str:
    return f"{PREFIX}-dr-{n}"


def email_bn(n: int) -> str:
    return f"{PREFIX}-patient{n}@example.com"


def email_bs(n: int) -> str:
    return f"{PREFIX}-doctor{n}@example.com"


# --------------------------------------------------------------------------- an toan
def kiem_tra_moi_truong() -> str:
    settings = get_settings()
    try:
        url = urlsplit(settings.database_url)
        host, db_name = url.hostname, (url.path or "").lstrip("/")
    except ValueError as exc:
        raise SystemExit(f"Tu choi: DATABASE_URL khong hop le ({exc}).") from exc
    if not host or not db_name:
        raise SystemExit("Tu choi: DATABASE_URL thieu host/ten DB.")
    if host not in HOST_LOCAL:
        raise SystemExit(f"Tu choi: chi seed vao DB local (host hien tai: {host}).")
    if settings.app_env == "production":
        raise SystemExit("Tu choi: APP_ENV=production.")
    cho_phep = {x.strip() for x in os.environ.get("CAPYMEDI_DEMO_ALLOWED_DBS", "capytest").split(",") if x.strip()}
    if db_name not in cho_phep:
        raise SystemExit(f"Tu choi: DB '{db_name}' khong nam trong CAPYMEDI_DEMO_ALLOWED_DBS={sorted(cho_phep)}.")
    mat_khau = os.environ.get("CAPYMEDI_DEMO_PASSWORD", "")
    if len(mat_khau) < 10:
        raise SystemExit("Tu choi: dat CAPYMEDI_DEMO_PASSWORD (>= 10 ky tu) trong env bi git ignore.")
    return mat_khau


# --------------------------------------------------------------------------- don dep
def xoa_du_lieu_demo(db) -> dict[str, int]:
    """Xoa DUNG cac dong co tien to demo. Bang khong co FK (convention repo);
    van lap vai luot + savepoint de khong ket neu sau nay them FK."""
    bang_cot = db.execute(text(
        "select table_name, column_name from information_schema.columns "
        "where table_schema='public' and column_name = any(:c)"), {"c": list(COT_DINH_DANH)}).all()
    presc_ids = [r[0] for r in db.execute(text("select id from prescription where patient_id like :p"), {"p": f"{PREFIX}%"})]
    lenh = [(t, f'delete from "{t}" where "{c}" like :p', {"p": f"{PREFIX}%"}) for t, c in bang_cot]
    lenh += [(t, f'delete from "{t}" where prescription_id = any(:ids)', {"ids": presc_ids})
             for t in ("prescription_item", "dose_event") if presc_ids]
    lenh += [("account", "delete from account where id like :p", {"p": f"{PREFIX}%"}),
             ("patient", "delete from patient where id like :p", {"p": f"{PREFIX}%"})]
    da_xoa: dict[str, int] = {}
    con_lai = lenh
    for _ in range(3):
        loi = []
        for t, sql, params in con_lai:
            sp = db.begin_nested()
            try:
                n = db.execute(text(sql), params).rowcount
                sp.commit()
                if n:
                    da_xoa[t] = da_xoa.get(t, 0) + n
            except Exception:  # noqa: BLE001 - thu lai o luot sau (thu tu FK)
                sp.rollback()
                loi.append((t, sql, params))
        con_lai = loi
        if not con_lai:
            break
    if con_lai:
        db.rollback()
        raise SystemExit(f"Khong don duoc: {[t for t, _, _ in con_lai]}")
    db.commit()
    return da_xoa


# --------------------------------------------------------------------------- API
def goi(api: str, method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json", INTERNAL_SECRET_HEADER: get_settings().internal_auth_secret}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    rq = urllib.request.Request(f"{api}/api/v1{path}", method=method, headers=headers,
                                data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(rq, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {path} -> {exc.code}: {exc.read().decode()[:300]}") from exc


def dang_nhap(api: str, email: str, mat_khau: str) -> str:
    return goi(api, "POST", "/auth/login", {"email": email, "password": mat_khau})["access_token"]


def item(drug_id: str, gio: list[str], ghi_chu: str) -> dict:
    return {"drug_id": drug_id, "lieu_dung": "1 viên/lần", "so_vien_moi_lan": 1, "gio_nhac": gio,
            "thoi_diem_dung": ghi_chu}


# --------------------------------------------------------------------------- lich su
def bo_sung_lieu_qua_khu(db, patient_id: str, tu_ngay: date, bay_gio: datetime) -> int:
    """Generator cua backend chi sinh lieu TU BAY GIO tro di (khong sinh lieu
    qua khu du start_date lui ngay). De co LICH SU hu cau, tao lieu cho cac ngay
    [tu_ngay, hom nay] da qua gio - sao chep prescription_id/expected_items/gio
    hen tu CHINH cac lieu backend da sinh (khong tu dat don thuoc)."""
    mau: dict[str, DoseEvent] = {}
    for d in db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id).all():
        mau.setdefault(d.scheduled_at.astimezone(VN).strftime("%H:%M"), d)
    da_co = {d.scheduled_at for d in db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id)}
    them = 0
    ngay = tu_ngay
    while ngay <= bay_gio.astimezone(VN).date():
        for hhmm, d in mau.items():
            h, m = map(int, hhmm.split(":"))
            hen = datetime(ngay.year, ngay.month, ngay.day, h, m, tzinfo=VN).astimezone(UTC)
            if hen + timedelta(minutes=30) < bay_gio and hen not in da_co:
                db.add(DoseEvent(prescription_id=d.prescription_id, patient_id=patient_id, scheduled_at=hen,
                                 window_start=hen - timedelta(minutes=30), window_end=hen + timedelta(minutes=30),
                                 status="PENDING", expected_items=d.expected_items))
                them += 1
        ngay += timedelta(days=1)
    db.flush()
    return them


def tao_lich_su(db, patient_id: str, kich_ban: str, bay_gio: datetime) -> None:
    """Chi dong vao lieu DA QUA khung xac nhan (window_end < bay gio)."""
    lieu = (db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id, DoseEvent.window_end < bay_gio)
            .order_by(DoseEvent.scheduled_at).all())
    for i, d in enumerate(lieu):
        if kich_ban == "dung_gio":
            d.status, d.first_reported_at = "TAKEN", d.scheduled_at + timedelta(minutes=5)
        elif kich_ban == "tre_bo_lieu":
            if i % 2 == 0:
                d.status, d.first_reported_at = "DELAYED", d.scheduled_at + timedelta(hours=2)
            else:
                d.status, d.first_reported_at = "MISSED", None
        # Diem: DUNG ham cua PATCH /doses/{id} (benh nhan tu bao) - liều tre bi
        # tru theo PCT_LATE_CONFIRMATION, tu bao giu PCT_SELF_REPORT_NO_PHOTO,
        # bo lieu khong phat. Khong tu tinh diem rieng o script.
        if d.status != "PENDING":
            _thuong_diem_neu_uong_du(
                db, dose_event_id=d.id, patient_id=patient_id, scheduled_at=d.scheduled_at,
                pct=_xac_dinh_ty_le_thuong(previous_status="PENDING", is_self_report=True,
                                           la_muon=d.status == "DELAYED", da_uong=d.status in {"TAKEN", "DELAYED"}),
            )
    db.commit()


def chuan_bi_bn3() -> None:
    """Truoc gio demo: dam bao BN3 co DUNG 1 lieu PENDING trong khung xac nhan
    (+5 phut). KHONG xoa/tao lai tai khoan, khong dong vao lich su: neu da co
    lieu dang trong khung thi khong lam gi; neu khong, doi lieu PENDING sap toi
    gan nhat ve (bay gio + 5 phut, khung +-30 phut)."""
    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        p3 = pid(3)
        dang_mo = db.query(DoseEvent).filter(DoseEvent.patient_id == p3, DoseEvent.status == "PENDING",
                                             DoseEvent.window_start <= now, DoseEvent.window_end >= now).first()
        if dang_mo is None:
            ke_tiep = (db.query(DoseEvent).filter(DoseEvent.patient_id == p3, DoseEvent.status == "PENDING",
                                                  DoseEvent.scheduled_at > now)
                       .order_by(DoseEvent.scheduled_at).first())
            if ke_tiep is None:
                raise SystemExit("BN3 khong con lieu PENDING nao - chay lai seed day du.")
            hen = now + timedelta(minutes=5)
            ke_tiep.scheduled_at, ke_tiep.window_start, ke_tiep.window_end = (
                hen, hen - timedelta(minutes=30), hen + timedelta(minutes=30))
            db.commit()
            dang_mo = ke_tiep
        print(json.dumps({"bn3_lieu_trong_khung": dang_mo.scheduled_at.astimezone(VN).strftime("%H:%M"),
                          "dose_id": dang_mo.id}, ensure_ascii=False))
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=os.environ.get("CAPYMEDI_DEMO_API_URL", "http://127.0.0.1:8001"))
    ap.add_argument("--chuan-bi-bn3", "--prepare-patient3", dest="chuan_bi_bn3", action="store_true",
                    help="Chi dua 1 lieu BN3 vao khung xac nhan.")
    ap.add_argument("--auto", action="store_true", help="Khoi tao NEU CHUA CO (an toan khi chay moi lan up).")
    ap.add_argument("--reset", action="store_true", help="Xoa + tao lai toan bo du lieu demo.")
    args = ap.parse_args()
    if args.auto:
        app_env = get_settings().app_env
        bat = os.environ.get("ENABLE_DEMO_SEED", "").strip().lower() == "true"
        if app_env != "demo" or not bat:
            print(f"[demo-seed] BO QUA: can APP_ENV=demo va ENABLE_DEMO_SEED=true (hien: {app_env}, {bat}).")
            return
    mat_khau = kiem_tra_moi_truong()
    if args.chuan_bi_bn3:
        chuan_bi_bn3()
        return
    if args.auto:
        db = SessionLocal()
        try:
            co = db.execute(text("select count(*) from account where id like :p"), {"p": f"{PREFIX}-%-acct"}).scalar()
        finally:
            db.close()
        if co == 6:
            print("[demo-seed] Du lieu demo DA CO (6 tai khoan) - bo qua, khong reset. "
                  "Muon tao lai: docker compose run --rm demo-seed --reset")
            return
        if co:
            raise SystemExit(f"[demo-seed] Chi co {co}/6 tai khoan demo - khong tu sua. Chay --reset neu chac chan.")
        print("[demo-seed] Chua co du lieu demo - khoi tao lan dau.")
        db = SessionLocal()
        try:
            so_thuoc = db.execute(text("select count(*) from drug")).scalar()
        finally:
            db.close()
        if not so_thuoc:
            # DB moi tinh: phac do demo can danh muc thuoc (drug_id). Nap bang
            # script SAN CO cua repo (chi chay khi bang drug TRONG).
            import subprocess

            print("[demo-seed] Bang drug trong - nap danh muc thuoc (scripts/seed_drug_catalog.py).")
            subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "seed_drug_catalog.py")], check=True)

    db = SessionLocal()
    try:
        da_xoa = xoa_du_lieu_demo(db)
        pw = hash_password(mat_khau)
        for d in DOCTORS:
            db.add(Account(id=acc_bs(d["n"]), full_name=d["name"], email=email_bs(d["n"]), password_hash=pw,
                           role="doctor", status="active", doctor_id=doctor_id(d["n"]), is_email_verified=True))
        for p in PATIENTS:
            db.add(Patient(id=pid(p["n"]), full_name=p["name"], date_of_birth=p["dob"], gender=p["gender"],
                           phone=f"09000000{p['n']:02d}", address="Hà Nội", height_cm=158, weight_kg=55,
                           doctor_id=doctor_id(p["n"]), photo_capture_enabled=True,
                           note="DỮ LIỆU DEMO HACKATHON — hư cấu"))
            db.add(Account(id=acc_bn(p["n"]), full_name=p["name"], email=email_bn(p["n"]), password_hash=pw,
                           role="patient", status="active", patient_id=pid(p["n"]), is_email_verified=True))
            db.add(DoctorWatch(doctor_id=doctor_id(p["n"]), patient_id=pid(p["n"])))
        db.commit()
    finally:
        db.close()

    bay_gio = datetime.now(VN)
    hom_nay = bay_gio.date()
    sap_toi = (bay_gio + timedelta(minutes=5)).strftime("%H:%M")
    don = {
        1: {"start": hom_nay - timedelta(days=2), "items": [
            item("amlodipin-5mg-truong-tho-3x10", ["08:00"], "Sau ăn sáng"),
            item("atorvastatin-10mg-tvp-3x10", ["20:00"], "Sau ăn tối")]},
        2: {"start": hom_nay - timedelta(days=2), "items": [
            item("metformin-500mg-stella-6x10", ["07:30", "19:30"], "Sau ăn")]},
        3: {"start": hom_nay, "items": [
            item("amlodipin-5mg-truong-tho-3x10", [sap_toi], "Sau ăn"),
            item("losartan-25mg-tvp-3x10", ["21:00"], "Buổi tối")]},
    }
    tokens = {d["n"]: dang_nhap(args.api, email_bs(d["n"]), mat_khau) for d in DOCTORS}
    presc: dict[str, str] = {}
    for n, cfg in don.items():
        tao = goi(args.api, "POST", "/prescriptions", {
            "patient_id": pid(n), "doctor_id": "bo-qua-vi-co-jwt", "start_date": cfg["start"].isoformat(),
            "duration_days": 7, "note": "Phác đồ demo hackathon", "items": cfg["items"]}, tokens[n])
        goi(args.api, "POST", f"/prescriptions/{tao['id']}/approve", {"doctor_id": "x"}, tokens[n])
        presc[f"BN{n}"] = tao["id"]

    db = SessionLocal()
    try:
        bay_gio_utc = datetime.now(UTC)
        lieu_lich_su = {}
        for p in PATIENTS:
            if p["kb"] in ("dung_gio", "tre_bo_lieu"):
                lieu_lich_su[pid(p["n"])] = bo_sung_lieu_qua_khu(db, pid(p["n"]), don[p["n"]]["start"], bay_gio_utc)
            tao_lich_su(db, pid(p["n"]), p["kb"], bay_gio_utc)
            for i in range(3):
                companion_service.tinh_lai_ngay(db, patient_id=pid(p["n"]), ngay=hom_nay - timedelta(days=i))
            db.commit()

        tong_ket = {}
        for p in PATIENTS:
            rows = db.query(DoseEvent).filter(DoseEvent.patient_id == pid(p["n"])).all()
            dem: dict[str, int] = {}
            for r in rows:
                dem[r.status] = dem.get(r.status, 0) + 1
            diem = db.execute(text("select spendable_points from patient_reward_account where patient_id=:p"),
                              {"p": pid(p["n"])}).scalar()
            units = db.execute(text("select coalesce(sum(units),0) from companion_care_day where patient_id=:p"),
                               {"p": pid(p["n"])}).scalar()
            hom_nay_gio = sorted(r.scheduled_at.astimezone(VN).strftime("%H:%M") for r in rows
                                 if r.scheduled_at.astimezone(VN).date() == hom_nay)
            tong_ket[email_bn(p["n"])] = {"kich_ban": p["kb"], "lieu_theo_trang_thai": dem,
                                          "lieu_hom_nay": hom_nay_gio, "diem": diem, "capy_units": int(units)}
        print(json.dumps({"da_xoa_ban_cu": da_xoa, "phac_do": presc, "lieu_lich_su_bo_sung": lieu_lich_su, "benh_nhan": tong_ket,
                          "bac_si": [email_bs(d["n"]) for d in DOCTORS]}, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
