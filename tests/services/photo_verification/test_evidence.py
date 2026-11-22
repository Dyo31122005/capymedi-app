"""TASK-CAPY-27 — kết quả xác minh ảnh có cấu trúc (hàm thuần, không DB/mạng).

OCR thật (Tesseract) KHÔNG chạy ở đây: dùng extractor giả trả văn bản lập trình
sẵn — test kiểm chứng tầng trích xuất/đối chiếu/quyết định, không kiểm chứng
chất lượng OCR (chưa có eval trên ảnh viên thuốc, xem evidence.py).
"""

from io import BytesIO

from PIL import Image

from backend.services.drug_image_recognition import OCR_AVAILABLE, OCR_UNAVAILABLE, OcrObservation  # noqa: F401
from backend.services.photo_verification import evidence as ev


def _anh(w=400, h=300, mau=(128, 128, 128), soc=True) -> bytes:
    img = Image.new("RGB", (w, h), mau)
    if soc:  # thêm cạnh để không bị coi là mờ
        for x in range(0, w, 8):
            for y in range(h):
                img.putpixel((x, y), (255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class _Ocr:
    def __init__(self, text, status=OCR_AVAILABLE):
        self.text, self.status = text, status

    def extract(self, _image):
        return OcrObservation(text=self.text, status=self.status)


PARA = [{"drug_id": "p1", "ten_thuoc": "Paracetamol 500mg", "dang_thuoc": "Viên nén", "so_vien": 1}]


# --- tầng 1: chất lượng ---------------------------------------------------
def test_anh_qua_nho_bi_tu_choi():
    q = ev.danh_gia_chat_luong(_anh(40, 40))
    assert q["status"] == "REJECT" and "IMAGE_TOO_SMALL" in q["reasons"]
    assert ev.anh_bi_tu_choi(q)


def test_anh_toi_chi_khuyen_chup_lai_khong_chan():
    q = ev.danh_gia_chat_luong(_anh(mau=(2, 2, 2), soc=False))
    assert q["status"] == "RETAKE_RECOMMENDED"
    assert not ev.anh_bi_tu_choi(q)


def test_anh_khong_giai_ma_duoc_khong_chan():
    q = ev.danh_gia_chat_luong(b"\xff\xd8\xff" + b"0" * 20)
    assert q["status"] == ev.QUALITY_NOT_ASSESSED
    assert not ev.anh_bi_tu_choi(q)


def test_anh_tot_pass():
    assert ev.danh_gia_chat_luong(_anh())["status"] == "PASS"


# --- tầng 2-4: OCR -> thực thể -> đối chiếu ------------------------------
def test_ocr_khop_ten_va_ham_luong():
    r = ev.trich_xuat_va_doi_chieu(_anh(), PARA, extractor=_Ocr("PARACETAMOL\n500 mg\nHop 10 vi"))
    assert r["ocr_status"] == OCR_AVAILABLE
    assert r["matched_prescription"] == {"drug_id": "p1", "name": "Paracetamol 500mg"}
    assert r["extracted"]["name"] == "Paracetamol 500mg"
    assert (r["extracted"]["strength"], r["extracted"]["unit"]) == ("500", "mg")
    assert r["mismatched_fields"] == []
    assert r["candidates"][0]["strength_match"] is True


def test_ocr_sai_ham_luong_ghi_mismatched_strength():
    r = ev.trich_xuat_va_doi_chieu(_anh(), PARA, extractor=_Ocr("Paracetamol 650mg"))
    assert r["mismatched_fields"] == ["strength"]
    assert r["candidates"][0]["strength_match"] is False


def test_ocr_khong_thay_ten_trong_don_la_not_found_khong_ket_luan_lech():
    # Biệt dược vs hoạt chất (PANADOL vs Paracetamol): "không thấy" != "sai thuốc".
    r = ev.trich_xuat_va_doi_chieu(_anh(), PARA, extractor=_Ocr("PANADOL\n500 mg"))
    assert r["matched_prescription"] is None
    assert r["name_status"] == "NOT_FOUND"
    assert r["mismatched_fields"] == []


def test_ten_co_so_vitamin_d3_khong_khop_nham_vitamin_c():
    don = [{"drug_id": "d3", "ten_thuoc": "Vitamin D3 1000 IU", "so_vien": 1}]
    r = ev.trich_xuat_va_doi_chieu(_anh(), don, extractor=_Ocr("VITAMIN C\n500mg"))
    assert r["name_status"] == "PARTIAL"
    assert r["matched_prescription"] is None and r["extracted"]["name"] is None
    assert r["mismatched_fields"] == ["strength"]
    r2 = ev.trich_xuat_va_doi_chieu(_anh(), don, extractor=_Ocr("VITAMIN D3\n1000 IU"))
    assert r2["name_status"] == "FOUND"
    assert (r2["extracted"]["strength"], r2["extracted"]["unit"]) == ("1000", "iu")


def test_ham_luong_nguy_hiem_duoc_phan_biet():
    for nhan, don, khop in (
        ("AMLODIPIN 0.5 mg", "Amlodipin 5mg", False),
        ("AMLODIPIN 0,5 mg", "Amlodipin 5mg", False),
        ("PARACETAMOL 50 mg", "Paracetamol 500mg", False),
        ("LEVOTHYROXIN 50 mcg", "Levothyroxin 50mg", False),
        ("PARACETAMOL 500mg", "Paracetamol 500 mg", True),
    ):
        r = ev.trich_xuat_va_doi_chieu(_anh(), [{"ten_thuoc": don}], extractor=_Ocr(nhan))
        assert r["candidates"][0]["strength_match"] is khop, nhan


def test_ocr_doc_mu_g_thanh_ng_khong_doan_thanh_mcg():
    # Tesseract đọc "µg" thành "ng"/"Hg" (eval). Không đoán — không kết luận.
    r = ev.trich_xuat_va_doi_chieu(_anh(), [{"ten_thuoc": "Levothyroxin 50mcg"}],
                                   extractor=_Ocr("LEVOTHYROXIN\n50 ng"))
    assert r["candidates"][0]["strength_match"] is None
    assert r["mismatched_fields"] == []


def test_hien_thi_ham_luong_uu_tien_gia_tri_trung_don():
    r = ev.trich_xuat_va_doi_chieu(_anh(), [{"ten_thuoc": "Vitamin D3 1000 IU"}],
                                   extractor=_Ocr("0 g\n98 g\nVITAMIN D3 1000 IU"))
    assert (r["extracted"]["strength"], r["extracted"]["unit"]) == ("1000", "iu")


def test_xoay_chu_doc_chi_khi_0_do_khong_co_chu():
    class _OcrTheoHuong:
        def extract(self, img):
            doc = img.width > img.height  # ảnh gốc dọc; xoay 90/270 -> ngang
            return OcrObservation(text="Paracetamol 500 mg" if doc else "~ =", status=OCR_AVAILABLE)

    goc_da_thu = []

    def _diem(img):
        goc_da_thu.append(img.size)
        return 300.0 if img.width > img.height else 0.0

    anh_doc = _anh(300, 600)
    r = ev.trich_xuat_va_doi_chieu(anh_doc, PARA, extractor=_OcrTheoHuong(), diem_chu=_diem)
    assert r["rotation"] in (90, 270) and r["name_status"] == "FOUND"
    # 0° đã đủ chữ -> không thử xoay
    goc_da_thu.clear()
    r0 = ev.trich_xuat_va_doi_chieu(_anh(), PARA, extractor=_Ocr("Paracetamol 500 mg"), diem_chu=lambda _i: 500.0)
    assert r0["rotation"] == 0
    # 0° không có chữ, xoay cũng không có -> giữ 0°, không bịa
    r1 = ev.trich_xuat_va_doi_chieu(anh_doc, PARA, extractor=_Ocr(""), diem_chu=lambda _i: 0.0)
    assert r1["rotation"] == 0 and r1["candidates"] == []


def test_mau_thuan_dang_vien_ocr_vlm_chi_bao_khong_doi_quyet_dinh():
    ocr = ev.trich_xuat_va_doi_chieu(_anh(), PARA, extractor=_Ocr("Paracetamol 500 mg\nViên nén"))
    assert ocr["ocr_forms"] == ["vien_nen"]
    r = ev.xay_dung_ket_qua(ket_qua="khop", confidence="cao", expected_by_form={"vien_nang": 1},
                            detected_by_form={"vien_nang": 1, "vien_nen": 0}, evidence={"ocr": ocr})
    assert r["verification_result"] == "MATCHED"  # quyết định đã duyệt giữ nguyên
    assert r["ocr_vlm_conflicts"] == ["form"] and r["ocr_conflict"] is True
    # VLM đếm vật chứa (hộp) -> không so dạng viên
    r2 = ev.xay_dung_ket_qua(ket_qua="khop", confidence="cao", expected_by_form={"hop_thuoc": 1},
                             detected_by_form={"hop_thuoc": 1}, evidence={"ocr": ocr})
    assert r2["ocr_vlm_conflicts"] == []


def test_ocr_khong_san_sang_tra_ve_rong_khong_raise():
    r = ev.trich_xuat_va_doi_chieu(_anh(), PARA, extractor=_Ocr("", OCR_UNAVAILABLE))
    assert r["ocr_status"] == OCR_UNAVAILABLE and r["candidates"] == [] and r["extracted"] is None


def test_ocr_loi_bat_ky_khong_raise():
    class _Hong:
        def extract(self, _):
            raise RuntimeError("boom")

    assert ev.trich_xuat_va_doi_chieu(_anh(), PARA, extractor=_Hong())["ocr_status"] == "OCR_FAILED"


def test_ocr_khop_ngang_hai_thuoc_la_multiple_candidates():
    don = [
        {"drug_id": "a", "ten_thuoc": "Paracetamol 500mg", "so_vien": 1},
        {"drug_id": "b", "ten_thuoc": "Paracetamol 325mg", "so_vien": 1},
    ]
    r = ev.trich_xuat_va_doi_chieu(_anh(), don, extractor=_Ocr("PARACETAMOL"))
    assert r["multiple_candidates"] is True
    assert r["matched_prescription"] is None and r["extracted"]["name"] is None
    # Có hàm lượng -> phân định được, không còn mơ hồ
    r2 = ev.trich_xuat_va_doi_chieu(_anh(), don, extractor=_Ocr("PARACETAMOL 325 mg"))
    assert r2["multiple_candidates"] is False
    assert r2["matched_prescription"]["drug_id"] == "b"
    kq = ev.xay_dung_ket_qua(ket_qua="do_tin_cay_thap", confidence="thap", expected_by_form={},
                             detected_by_form={}, evidence={"ocr": r})
    assert kq["uncertainty_reason"] == "MULTIPLE_CANDIDATES"


# --- tầng 5: quyết định ---------------------------------------------------
def _kq(ket_qua, evidence=None, exp=None, det=None, conf="cao"):
    return ev.xay_dung_ket_qua(
        ket_qua=ket_qua, confidence=conf, expected_by_form=exp or {"vien_nen": 1},
        detected_by_form=det or {"vien_nen": 1}, evidence=evidence,
    )


def test_dang_xu_ly_tra_none():
    assert _kq("dang_xu_ly") is None


def test_khop_la_matched_va_khong_chung_minh_da_uong():
    r = _kq("khop")
    assert r["verification_result"] == "MATCHED"
    assert r["uncertainty_reason"] is None
    assert r["proves_ingestion"] is False
    assert r["extracted"]["form"] == "vien_nen"
    assert r["evidence_source"] == ["VLM_COUNT"]


def test_lech_la_mismatched_co_truong_lech():
    r = _kq("lech", det={"vien_nen": 2})
    assert r["verification_result"] == "MISMATCHED"
    assert r["mismatched_fields"] == ["count:vien_nen"]


def test_cac_truong_hop_uncertain():
    assert _kq("khong_xac_minh_duoc")["uncertainty_reason"] == "UNKNOWN"
    assert _kq("do_tin_cay_thap")["uncertainty_reason"] == "UNCERTAIN"
    assert _kq("loi_he_thong")["uncertainty_reason"] == "SYSTEM_ERROR"
    r = _kq("do_tin_cay_thap", evidence={"image_quality": {"status": "REJECT"}, "rejected_by_quality": True})
    assert r["verification_result"] == "UNCERTAIN"
    assert r["uncertainty_reason"] == "INSUFFICIENT_IMAGE"
    assert r["evidence_source"] == ["QUALITY_GATE"]


def test_ocr_mau_thuan_khi_dem_khop_chi_canh_bao_khong_doi_quyet_dinh():
    ocr = ev.trich_xuat_va_doi_chieu(_anh(), PARA, extractor=_Ocr("Paracetamol 650mg"))
    r = _kq("khop", evidence={"image_quality": {"status": "PASS"}, "ocr": ocr})
    assert r["verification_result"] == "MATCHED"  # bộ đếm (đã eval) vẫn quyết định
    assert r["ocr_conflict"] is True
    assert r["mismatched_fields"] == ["strength"]
    assert r["evidence_source"] == ["QUALITY_GATE", "VLM_COUNT", "OCR"]


def test_dong_cu_khong_co_evidence_van_suy_duoc():
    r = _kq("khop", evidence=None)
    assert r["verification_result"] == "MATCHED" and r["image_quality"] is None and r["candidates"] == []
