"""Eval OCR bang chung ten/ham luong (TASK-CAPY-28) qua DUNG code production:
nen_anh -> evidence.trich_xuat_va_doi_chieu (Tesseract that + buoc xoay).

Hai phan, KHONG gop so lieu:
  A. Nhan TONG HOP (render chu, ground truth biet truoc) - kiem chung engine +
     parse ham luong (0.5/5 mg, 50/500 mg, mg/mcg, IU, biet duoc...).
  B. Anh golden set eval/eval_vlm/anh_test (anh chup that cua team, KHONG phai
     anh benh nhan) - ground truth ten/ham luong GHI TAY tu anh.

Can Tesseract + vie/eng tren PATH. Chay:
    python eval/eval_ocr/run_eval_ocr.py
"""

from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.services.photo_verification import evidence as ev  # noqa: E402
from backend.services.photo_verification.image_processing import nen_anh  # noqa: E402

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# (id, dong chu tren nhan, ten_thuoc trong don, strength_match ky vong, name_status ky vong)
TONG_HOP = [
    ("S1", ["AMLODIPIN", "5 mg", "Viên nén"], "Amlodipin 5mg", True, "FOUND"),
    ("S2", ["AMLODIPIN", "0.5 mg", "Viên nén"], "Amlodipin 5mg", False, "FOUND"),
    ("S3", ["AMLODIPIN", "0,5 mg"], "Amlodipin 5mg", False, "FOUND"),
    ("S4", ["PARACETAMOL", "50 mg"], "Paracetamol 500mg", False, "FOUND"),
    ("S5", ["PARACETAMOL 500mg"], "Paracetamol 500mg", True, "FOUND"),
    ("S6", ["LEVOTHYROXIN", "50 mcg"], "Levothyroxin 50mg", False, "FOUND"),
    ("S7", ["LEVOTHYROXIN", "50 µg"], "Levothyroxin 50mcg", None, "FOUND"),  # µg -> "ng"/"Hg": khong doan
    ("S8", ["VITAMIN D3", "1000 IU"], "Vitamin D3 1000 IU", True, "FOUND"),
    ("S9", ["PANADOL", "500 mg"], "Paracetamol 500mg", None, "NOT_FOUND"),  # biet duoc vs hoat chat
    ("S10", ["AMOXICILLIN 500 mg", "Viên nang cứng"], "Amoxicillin 500mg", True, "FOUND"),
    ("S11", ["Paracetamol 325 mg", "Tramadol 37,5 mg"], "Paracetamol 500mg", False, "FOUND"),
    ("S12", ["METFORMIN", "850 mg", "Hộp 10 vỉ x 10 viên"], "Metformin 850mg", True, "FOUND"),
]

# Ground truth ghi tay tu anh golden set (chi anh co nhan doc duoc bang mat).
THAT = {
    5: ("Pharmaton Kiddi", "nhan nho, siro"),
    6: ("Adacine 15 g", "tuyp gel cam DOC"),
    14: ("Vitamin C 500mg", "2 chai: Xylatol 500 mg (keo) + Vitamin C 500mg"),
    15: ("Vitamin D3 1000 IU", "Vitamin D3 1000 IU + bang dinh duong"),
    19: ("Smecta 3 g", "goi Smecta, Diosmectite 3 g, chu nho"),
}


def _nhan(lines: list[str], size: int) -> bytes:
    f = ImageFont.truetype(FONT, size)
    w = max(int(f.getlength(t)) for t in lines) + 80
    im = Image.new("RGB", (w, (size + 24) * len(lines) + 60), "white")
    d = ImageDraw.Draw(im)
    for k, t in enumerate(lines):
        d.text((40, 30 + k * (size + 24)), t, font=f, fill=(20, 30, 90))
    b = BytesIO()
    im.save(b, format="JPEG", quality=85)
    return b.getvalue()


def main() -> None:
    s = get_settings()
    dung = tong = 0
    print("A. NHAN TONG HOP")
    for size in (48, 22):
        for cid, lines, don, sm, ns in TONG_HOP:
            r = ev.trich_xuat_va_doi_chieu(nen_anh(_nhan(lines, size), s.photo_max_edge_px, s.photo_jpeg_quality),
                                           [{"drug_id": "x", "ten_thuoc": don}])
            c = r["candidates"][0] if r["candidates"] else {}
            ok = c.get("strength_match") == sm and r["name_status"] == ns
            dung += ok
            tong += 1
            print(f"  {size:>2}px {cid:<4} {'OK   ' if ok else 'SAI  '} doc={c.get('strength_observed')} "
                  f"strength_match={c.get('strength_match')} name_status={r['name_status']} forms={r['ocr_forms']}")
    print(f"  => {dung}/{tong} dung ky vong\n")

    print("B. ANH GOLDEN SET (ground truth ghi tay)")
    anh_dir = ROOT / "eval/eval_vlm/anh_test"
    for p in sorted(anh_dir.iterdir(), key=lambda p: int(p.stem.split("_")[1])):
        i = int(p.stem.split("_")[1])
        don, ghi_chu = THAT.get(i, ("(vien thuoc roi, khong co nhan)", ""))
        r = ev.trich_xuat_va_doi_chieu(nen_anh(p.read_bytes(), s.photo_max_edge_px, s.photo_jpeg_quality),
                                       [{"drug_id": "x", "ten_thuoc": don}])
        e = r["extracted"] or {}
        print(f"  anh_{i:<2} don={don:<32} name_status={r['name_status']:<9} "
              f"ham_luong={e.get('strength')}{e.get('unit') or ''} xoay={r['rotation']} forms={r['ocr_forms']} {ghi_chu}")


if __name__ == "__main__":
    main()
