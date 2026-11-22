"""TASK-CAPY-28 — chạy Tesseract THẬT (không giả lập) trên nhãn TỔNG HỢP.

Chỉ kiểm chứng ENGINE + parse (render chữ có ground truth biết trước), KHÔNG
phải đánh giá nhận diện thuốc trên ảnh thật. Tự skip khi máy không có
Tesseract + vie/eng (vd CI hiện tại) — vì vậy file này KHÔNG nằm trong job CI
"fail on any skip". Chạy local: PATH chứa binary tesseract.
"""

from io import BytesIO

import pytest
from PIL import Image, ImageDraw, ImageFont

from backend.services.drug_image_recognition import OCR_AVAILABLE, OptionalTesseractOcrExtractor
from backend.services.photo_verification import evidence as ev

_EX = OptionalTesseractOcrExtractor()
_rt, _status = _EX._resolve_runtime()
pytestmark = pytest.mark.skipif(_status != OCR_AVAILABLE, reason=f"Tesseract không sẵn sàng ({_status})")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _nhan(lines, size=40, xoay=0) -> bytes:
    f = ImageFont.truetype(FONT, size)
    w = max(int(f.getlength(t)) for t in lines) + 80
    im = Image.new("RGB", (w, (size + 24) * len(lines) + 60), "white")
    d = ImageDraw.Draw(im)
    for k, t in enumerate(lines):
        d.text((40, 30 + k * (size + 24)), t, font=f, fill=(20, 30, 90))
    if xoay:
        im = im.rotate(xoay, expand=True, fillcolor="white")
    b = BytesIO()
    im.save(b, format="JPEG", quality=85)
    return b.getvalue()


@pytest.mark.parametrize(
    "lines,don,khop",
    [
        (["AMLODIPIN", "5 mg"], "Amlodipin 5mg", True),
        (["AMLODIPIN", "0.5 mg"], "Amlodipin 5mg", False),
        (["PARACETAMOL", "50 mg"], "Paracetamol 500mg", False),
        (["LEVOTHYROXIN", "50 mcg"], "Levothyroxin 50mg", False),
        (["VITAMIN D3", "1000 IU"], "Vitamin D3 1000 IU", True),
    ],
)
def test_tesseract_that_trich_ten_va_ham_luong(lines, don, khop):
    r = ev.trich_xuat_va_doi_chieu(_nhan(lines), [{"drug_id": "x", "ten_thuoc": don}])
    assert r["ocr_status"] == OCR_AVAILABLE
    assert r["name_status"] == "FOUND"
    assert r["candidates"][0]["strength_match"] is khop


def test_tesseract_that_doc_duoc_nhan_xoay_doc():
    # Nhãn quay 90° (như tuýp thuốc cầm dọc) — 0° không đọc được, bước xoay cứu.
    r = ev.trich_xuat_va_doi_chieu(_nhan(["AMLODIPIN 5 mg", "Viên nén"], size=44, xoay=90),
                                   [{"drug_id": "x", "ten_thuoc": "Amlodipin 5mg"}])
    assert r["rotation"] in (90, 270)
    assert r["name_status"] == "FOUND" and r["candidates"][0]["strength_match"] is True
    assert r["ocr_forms"] == ["vien_nen"]
