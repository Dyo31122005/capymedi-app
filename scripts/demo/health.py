#!/usr/bin/env python3
"""Kiem tra suc khoe stack demo - chi bao HEALTHY khi DA KIEM TRA THAT.

Trang thai: HEALTHY | UNHEALTHY | UNAVAILABLE | NOT CONFIGURED | UNVERIFIED
  - VLM: khong goi provider tru khi co `--probe-vlm` (moi lan goi ton tien) ->
    da cau hinh nhung chua goi thu = UNVERIFIED, khong phai HEALTHY.

Chay (Docker):  docker compose exec backend python scripts/demo/health.py [--probe-vlm]
Khong in gia tri bi mat.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TRONG_DOCKER = Path("/.dockerenv").exists()
BE = os.environ.get("HEALTH_BACKEND_URL", "http://localhost:8000" if TRONG_DOCKER else "http://127.0.0.1:8001")
FE = os.environ.get("HEALTH_FRONTEND_URL", "http://frontend:3000" if TRONG_DOCKER else "http://localhost:3010")
ket_qua: list[tuple[str, str, str]] = []


def ghi(muc: str, trang_thai: str, chi_tiet: str = "") -> None:
    ket_qua.append((muc, trang_thai, chi_tiet))


def http(url: str, method: str = "GET", body: dict | None = None, token: str | None = None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    rq = urllib.request.Request(url, method=method, headers=h, data=json.dumps(body).encode() if body else None)
    try:
        with urllib.request.urlopen(rq, timeout=15) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, None
    except urllib.error.HTTPError as e:
        return e.code, None
    except OSError as e:
        return 0, str(e)


def kiem_tra_vlm(probe: bool) -> None:
    from backend.config import get_settings
    from backend.services.photo_verification.vlm_bridge import _khoa_vlm

    s = get_settings()
    la_openai = not s.vlm_base_url or "api.openai.com" in s.vlm_base_url
    if not s.vlm_model or (la_openai and _khoa_vlm(s) == "not-needed"):
        ghi("VLM (AI dem thuoc)", "NOT CONFIGURED", "can VLM_MODEL (+ OPENAI_API_KEY voi provider openai)")
        return
    nguon = "OPENAI_API_KEY" if (la_openai and not s.vlm_api_key) else "VLM_API_KEY"
    if not probe:
        ghi("VLM (AI dem thuoc)", "UNVERIFIED", f"{s.vlm_model} qua {nguon} - chay them --probe-vlm de goi that")
        return
    from backend.services.photo_verification.image_processing import nen_anh
    from backend.services.photo_verification.vlm_bridge import dem_thuoc_trong_anh

    anh_dir = ROOT / "eval/eval_vlm/anh_test"
    anh = anh_dir / "anh_1.jpg"
    if not anh.exists():  # image backend loai eval/ khoi build context -> dung anh nhan tong hop
        from io import BytesIO

        from PIL import Image, ImageDraw

        im = Image.new("RGB", (640, 480), "white")
        ImageDraw.Draw(im).ellipse((260, 180, 380, 300), fill=(240, 240, 235), outline=(120, 120, 120), width=4)
        b = BytesIO()
        im.save(b, format="JPEG")
        du_lieu = b.getvalue()
    else:
        du_lieu = anh.read_bytes()
    kq = dem_thuoc_trong_anh(nen_anh(du_lieu, s.photo_max_edge_px, s.photo_jpeg_quality))
    if kq.ok:
        ghi("VLM (AI dem thuoc)", "HEALTHY", f"{s.vlm_model}: goi that OK {kq.latency_sec:.1f}s, do_tin_cay={kq.do_tin_cay}")
    else:
        ghi("VLM (AI dem thuoc)", "UNHEALTHY", (kq.error or "loi")[:90])


def main() -> int:
    probe = "--probe-vlm" in sys.argv
    st, _ = http(f"{BE}/health")
    ghi("Backend FastAPI", "HEALTHY" if st == 200 else "UNHEALTHY", BE)

    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import text

        from backend.db.base import SessionLocal

        db = SessionLocal()
        cur = db.execute(text("select version_num from alembic_version")).scalar()
        head = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_current_head()
        n_drug = db.execute(text("select count(*) from drug")).scalar()
        n_demo = db.execute(text("select count(*) from account where id like 'hackathon-demo-%-acct'")).scalar()
        ten_db = db.execute(text("select current_database()")).scalar()
        db.close()
        ghi("PostgreSQL", "HEALTHY", f"database={ten_db}")
        ghi("Migration", "HEALTHY" if cur == head else "UNHEALTHY", f"DB={cur} head={head}")
        ghi("Danh muc thuoc", "HEALTHY" if n_drug else "UNHEALTHY", f"{n_drug} thuoc")
        ghi("Du lieu demo", "HEALTHY" if n_demo == 6 else ("NOT CONFIGURED" if n_demo == 0 else "UNHEALTHY"),
            f"{n_demo}/6 tai khoan")
    except Exception as exc:  # noqa: BLE001
        ghi("PostgreSQL", "UNHEALTHY", type(exc).__name__)

    st, _ = http(f"{FE}/login")
    ghi("Frontend Next.js", "HEALTHY" if st == 200 else "UNHEALTHY", FE)

    exe = shutil.which("tesseract")
    if not exe:
        ghi("OCR Tesseract", "UNAVAILABLE", "khong co tren PATH")
    else:
        langs = set(subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=10).stdout.split())
        ghi("OCR Tesseract", "HEALTHY" if {"vie", "eng"} <= langs else "UNHEALTHY",
            "vie+eng" if {"vie", "eng"} <= langs else "thieu goi ngon ngu")
    ocr_bat = os.environ.get("PHOTO_OCR_EVIDENCE_ENABLED", "").lower() == "true"
    ghi("OCR bang chung", "HEALTHY" if ocr_bat else "NOT CONFIGURED", "PHOTO_OCR_EVIDENCE_ENABLED")

    kiem_tra_vlm(probe)

    pw = os.environ.get("CAPYMEDI_DEMO_PASSWORD")
    if not pw:
        ghi("Companion (nhom demo)", "NOT CONFIGURED", "thieu CAPYMEDI_DEMO_PASSWORD")
    else:
        st, body = http(f"{BE}/api/v1/auth/login", "POST",
                        {"email": "hackathon-demo-patient1@example.com", "password": pw})
        if st == 200 and isinstance(body, dict):
            st2, comp = http(f"{BE}/api/v1/companion/me", token=body["access_token"])
            bat = st2 == 200 and isinstance(comp, dict) and comp.get("enabled")
            ghi("Dang nhap demo (BN1)", "HEALTHY", "")
            ghi("Companion (nhom demo)", "HEALTHY" if bat else "NOT CONFIGURED", "COMPANION_ENABLED + ALLOWLIST")
        else:
            ghi("Dang nhap demo (BN1)", "UNHEALTHY" if st else "UNAVAILABLE", f"HTTP {st}")

    w = max(len(m) for m, _, _ in ket_qua)
    for m, t, c in ket_qua:
        print(f"  {m:<{w}}  {t:<14}  {c}")
    return 0 if all(t != "UNHEALTHY" for _, t, _ in ket_qua) else 1


if __name__ == "__main__":
    sys.exit(main())
