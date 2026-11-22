"""Kết quả xác minh ảnh CÓ CẤU TRÚC (TASK-CAPY-27).

Tách rõ các tầng của pipeline ảnh — trước đây chỉ có một chuỗi `ket_qua`:

  1. chat_luong_anh   — kiểm tra tất định (kích thước/tỉ lệ/độ sáng/độ nét),
                        dùng lại `drug_image_recognition.inspect_image_quality`.
  2. trich_xuat_chu   — OCR cục bộ (Tesseract, adapter có sẵn), CHỈ khi bật cờ
                        `photo_ocr_evidence_enabled`. Không lưu văn bản thô.
  3. trich_xuat_thuc_the — tên/hàm lượng/đơn vị từ chữ OCR
                        (`extract_structured_signals`).
  4. doi_chieu_don    — so tên/hàm lượng OCR với `dose_event.expected_items`.
  5. quyet_dinh       — MATCHED / MISMATCHED / UNCERTAIN.
  6. xác nhận uống    — KHÔNG nằm ở đây: nhận diện đúng thuốc không chứng minh
                        đã uống. Xem specs/business-rules.md BR-4.9.

QUAN TRỌNG — ai quyết định:
  `verification_result` vẫn suy từ bộ đối chiếu SỐ LƯỢNG theo dạng bào chế
  (matcher.py, ADR-0011) — đây là logic đã qua eval golden set. Bằng chứng OCR
  chỉ là TƯ VẤN: nó không đổi `ket_qua`, không đổi trạng thái liều, không đổi
  điểm. Lý do: OCR chưa được eval trên ảnh viên thuốc rời (ADR-0004 §10 bắt buộc
  eval trước khi để một tín hiệu mới quyết định). Khi OCR đọc được hàm lượng
  KHÁC đơn, ta ghi `mismatched_fields=["strength"]` và `ocr_conflict=True` để
  bác sĩ/QA thấy — không âm thầm sửa quyết định lâm sàng.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from io import BytesIO
from typing import Any

from PIL import Image

from backend.services.drug_image_recognition import (
    OCR_AVAILABLE,
    OCR_NOT_RUN,
    QUALITY_REJECT,
    OcrExtractor,
    OcrObservation,
    OptionalTesseractOcrExtractor,
    _load_pytesseract,
    extract_structured_signals,
    inspect_image_quality,
    normalize_for_match,
    normalize_visible_text,
)

logger = logging.getLogger(__name__)

# --- giá trị công khai (api-contracts.md §5, trường `verification`) ---------
MATCHED = "MATCHED"
MISMATCHED = "MISMATCHED"
UNCERTAIN = "UNCERTAIN"

# Lý do khi UNCERTAIN (mô hình/pipeline được phép trả lời "không biết").
REASON_UNKNOWN = "UNKNOWN"  # dạng thuốc không kiểm được bằng ảnh / không có gì để so
REASON_UNCERTAIN = "UNCERTAIN"  # mô hình tự báo không chắc
REASON_INSUFFICIENT_IMAGE = "INSUFFICIENT_IMAGE"  # ảnh không đạt chất lượng tối thiểu
REASON_MULTIPLE_CANDIDATES = "MULTIPLE_CANDIDATES"  # OCR khớp nhiều thuốc khác nhau, không phân định được
REASON_SYSTEM_ERROR = "SYSTEM_ERROR"  # lỗi hạ tầng, không có kết quả để đối chiếu

QUALITY_NOT_ASSESSED = "NOT_ASSESSED"

EVIDENCE_VLM_COUNT = "VLM_COUNT"
EVIDENCE_OCR = "OCR"
EVIDENCE_QUALITY_GATE = "QUALITY_GATE"

# Trang thai VLM THAT cua lan xac minh (audit 2026-11-14) - de UI tach ro "OCR
# that da chay" voi "AI dem thuoc co chay khong", khong bao gio gia lap.
VLM_OK = "OK"
VLM_UNAVAILABLE = "UNAVAILABLE"  # may chu chua cau hinh VLM_MODEL/VLM_API_KEY
VLM_ERROR = "ERROR"  # da goi nhung loi mang/model

THONG_BAO_VLM_CHUA_BAT = (
    "AI đếm thuốc chưa được bật trên máy chủ này nên chưa đối chiếu được số viên. "
    "Ảnh không bị tính vào lượt chụp. Bạn có thể xác nhận thủ công trong \"Tùy chọn khác\"."
)

# Câu nói với bệnh nhân khi ảnh không đọc được (yêu cầu PO 2026-11-14).
THONG_BAO_ANH_KHONG_RO = (
    "Chưa đọc rõ thông tin thuốc. Vui lòng thử chụp gần hơn hoặc chụp mặt có tên thuốc."
)

_STOPWORDS = frozenset({"vien", "nen", "nang", "thuoc", "mg", "ml", "mcg", "g", "goi", "lo", "hop", "tuyp"})

# Hàm lượng: giống `drug_image_recognition._STRENGTH_PATTERN` + đơn vị IU/UI
# (eval OCR 2026-11-14: nhãn "1000 IU" đọc ĐÚNG nhưng bị bỏ qua vì thiếu đơn
# vị). Giữ pattern dùng chung không đổi để không ảnh hưởng nhận diện vỏ hộp.
# CỐ Ý KHÔNG ánh xạ "ng"/"Hg" -> mcg: Tesseract đọc "µg" thành "ng"/"Hg" trong
# eval, mà "ng" (nanogram) là đơn vị thật — đoán sẽ thành fuzzy match nguy hiểm.
_HAM_LUONG = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*(mcg|µg|ug|mg|ml|g|%|iu|ui)(?!\w)", re.IGNORECASE)
_DON_VI_CHUAN = {"µg": "mcg", "ug": "mcg", "ui": "iu"}

# Dạng viên ĐỌC ĐƯỢC trên nhãn -> khoá đếm của VLM (prompts.COUNT_KEYS).
# Chỉ 2 dạng viên dễ nhầm lâm sàng; hộp/lọ/tuýp do VLM đếm vật chứa nên không so.
_DANG_VIEN_OCR = {"vien nen": "vien_nen", "vien nang": "vien_nang"}

# Xoay chữ dọc (eval anh_6: nhãn tuýp thuốc cầm dọc, 0° chỉ ra rác, 270° đọc
# được "Gel bôi da | Tuýp 15 g"). OSD của Tesseract cho HƯỚNG SAI trên chính ảnh
# đó (conf 0.64) nên không dùng OSD. Chỉ thử xoay khi 0° gần như KHÔNG có chữ
# tin cậy; ảnh nhiều chữ (anh_15) có điểm 270° ≈ 0° nên không được chọn argmax.
_DIEM_CHU_TOI_THIEU = 100.0
_GOC_THU = (90, 270)


def danh_gia_chat_luong(anh: bytes) -> dict[str, Any]:
    """Tầng 1. Tất định, không gọi mạng. Trả dict để lưu thẳng vào JSON."""
    try:
        with Image.open(BytesIO(anh)) as img:
            q = inspect_image_quality(img)
    except (OSError, ValueError):
        # Ảnh thật luôn đã qua `nen_anh` (decode + re-encode) lúc nhận, nên
        # nhánh này gần như chỉ gặp với dữ liệu bất thường. KHÔNG chặn: để VLM
        # xử lý như trước (giữ hành vi cũ), chỉ ghi là chưa đánh giá được.
        return {"status": QUALITY_NOT_ASSESSED, "reasons": ["IMAGE_UNREADABLE"], "width": None, "height": None}
    return {"status": q.status, "reasons": list(q.reason_codes), "width": q.width, "height": q.height}


def anh_bi_tu_choi(chat_luong: Mapping[str, Any]) -> bool:
    """Chỉ REJECT (quá nhỏ/tỉ lệ cực đoan/không đọc được) mới chặn trước VLM.

    RETAKE_RECOMMENDED (tối/mờ) KHÔNG chặn: ngưỡng của inspect_image_quality
    được chỉnh cho ảnh vỏ hộp, chưa eval trên ảnh viên thuốc rời — chặn ở đây
    có thể từ chối oan ảnh hợp lệ. Chỉ ghi vào bằng chứng.
    """
    return chat_luong.get("status") == QUALITY_REJECT


def _ham_luong(text: str) -> set[str]:
    out: set[str] = set()
    for m in _HAM_LUONG.finditer(normalize_visible_text(text)):
        amount = f"{float(m.group(1).replace(',', '.')):g}"  # "500.0" -> "500", "0,5" -> "0.5"
        unit = _DON_VI_CHUAN.get(m.group(2).casefold(), m.group(2).casefold())
        out.add(f"{amount} {unit}")
    return out


def _dang_vien(text: str) -> list[str]:
    norm = f" {normalize_for_match(text)} "
    return sorted({k for cum, k in _DANG_VIEN_OCR.items() if f" {cum} " in norm})


def _diem_chu(img: Image.Image) -> float:
    """Tổng độ tin cậy các từ >=3 chữ cái, conf>=70 (Tesseract image_to_data)."""
    rt = _load_pytesseract()
    d = rt.image_to_data(img.convert("L"), lang="vie+eng", timeout=10, output_type=rt.Output.DICT)
    return sum(
        float(c) for w, c in zip(d["text"], d["conf"], strict=False)
        if float(c) >= 70 and sum(ch.isalpha() for ch in w) >= 3
    )


def _ocr_co_xoay(img: Image.Image, extractor: OcrExtractor, diem_chu) -> tuple[OcrObservation, int]:
    """OCR 0°; nếu gần như không có chữ, thử 90/270 và GỘP văn bản hướng tốt nhất."""
    obs = extractor.extract(img)
    if obs.status != OCR_AVAILABLE or diem_chu is None:
        return obs, 0
    try:
        if diem_chu(img) >= _DIEM_CHU_TOI_THIEU:
            return obs, 0
        diem = {g: diem_chu(img.rotate(g, expand=True)) for g in _GOC_THU}
    except Exception:  # noqa: BLE001 - bước phụ, lỗi thì giữ kết quả 0°
        logger.warning("OCR rotation probe failed", exc_info=True)
        return obs, 0
    goc = max(diem, key=diem.get)
    if diem[goc] < _DIEM_CHU_TOI_THIEU:
        return obs, 0
    xoay = extractor.extract(img.rotate(goc, expand=True))
    text = "\n".join(t for t in (obs.text, xoay.text) if t)
    return OcrObservation(text=text, status=obs.status), goc


def _tu_khoa_ten(ten: str) -> set[str]:
    """Token tên thuốc có nghĩa (bỏ số, đơn vị, từ chung).

    Giữ token chữ+số ("d3", "b12", "q10"): eval anh_14 — bỏ "d3" khiến đơn
    "Vitamin D3" khớp 100% nhãn "VITAMIN C" (nhận nhầm thuốc).
    """
    tokens = normalize_for_match(_HAM_LUONG.sub(" ", normalize_visible_text(ten))).split()
    return {
        t for t in tokens
        if t not in _STOPWORDS and (
            (len(t) >= 4 and t.isalpha())
            or (len(t) >= 2 and any(ch.isalpha() for ch in t) and any(ch.isdigit() for ch in t))
        )
    }


def _don_vi(ham_luong: str | None) -> tuple[str | None, str | None]:
    if not ham_luong:
        return None, None
    so, _, dv = ham_luong.partition(" ")
    return so or None, dv or None


def trich_xuat_va_doi_chieu(
    anh: bytes,
    expected_items: Iterable[Mapping[str, Any]],
    *,
    extractor: OcrExtractor | None = None,
    diem_chu=None,
) -> dict[str, Any]:
    """Tầng 2-4: OCR -> thực thể -> đối chiếu đơn. Không bao giờ raise.

    `diem_chu`: hàm chấm điểm chữ cho bước thử xoay; mặc định dùng Tesseract
    thật khi `extractor` là mặc định, tắt (None) khi test truyền extractor giả.
    """
    items = list(expected_items)
    if extractor is None:
        extractor = OptionalTesseractOcrExtractor()
        diem_chu = diem_chu or _diem_chu
    try:
        with Image.open(BytesIO(anh)) as img:
            img.load()
            obs, goc = _ocr_co_xoay(img, extractor, diem_chu)
    except Exception:  # noqa: BLE001 - OCR là tư vấn, lỗi không được làm hỏng xác minh
        logger.warning("OCR evidence failed", exc_info=True)
        return _ocr_rong("OCR_FAILED")
    if obs.status != OCR_AVAILABLE or not obs.text.strip():
        return _ocr_rong(obs.status, goc)

    signals = extract_structured_signals(obs.text)
    hl_quan_sat = sorted(_ham_luong(obs.text))
    observed_tokens = set(normalize_for_match(obs.text).split())

    candidates: list[dict[str, Any]] = []
    for item in items:
        ten = str(item.get("ten_thuoc") or "")
        tk = _tu_khoa_ten(ten)
        if not tk:
            continue
        trung = tk & observed_tokens
        if not trung:
            continue
        hl_don = _ham_luong(ten) | _ham_luong(str(item.get("ham_luong") or ""))
        hl_anh = set(hl_quan_sat)
        if hl_don and hl_anh:
            strength_match: bool | None = bool(hl_don & hl_anh)
        else:
            strength_match = None  # thiếu một phía -> không kết luận
        candidates.append({
            "drug_id": item.get("drug_id"),
            "name": ten,
            "name_score": round(len(trung) / len(tk), 2),
            "strength_expected": sorted(hl_don) or None,
            "strength_observed": sorted(hl_anh) or None,
            "strength_match": strength_match,
        })
    # Xếp: hàm lượng khớp trước, rồi điểm tên.
    candidates.sort(key=lambda c: (c["strength_match"] is True, c["name_score"]), reverse=True)

    # Hai thuốc trong đơn khớp NGANG nhau (cùng điểm tên, hàm lượng không tách
    # được - vd "Paracetamol 500mg" và "Paracetamol 325mg" mà ảnh chỉ thấy chữ
    # PARACETAMOL) -> không phân định được thuốc nào, không chọn bừa.
    multiple = (
        len(candidates) >= 2
        and candidates[0]["name_score"] == candidates[1]["name_score"]
        and candidates[0]["strength_match"] is not True
    )
    top = candidates[0] if candidates and not multiple else None
    # Chỉ nhận là ĐÚNG tên khi khớp ĐỦ mọi token tên trong đơn; khớp một phần
    # (vd "Vitamin D3" vs nhãn chỉ thấy "VITAMIN") -> PARTIAL, không gán thuốc.
    partial = top is not None and top["name_score"] < 1.0
    mismatched: list[str] = []
    if top and top["strength_match"] is False:
        mismatched.append("strength")
    # KHÔNG kết luận lệch tên khi không thấy tên trong đơn: eval cho thấy nhãn
    # biệt dược ("PANADOL" vs đơn "Paracetamol") và dòng chữ phụ ("Gel bôi da",
    # "THUỐC KÊ ĐƠN") đều rơi vào đây — "không tìm thấy" != "sai thuốc".
    if top and not partial:
        name_status = "FOUND"
    elif partial:
        name_status = "PARTIAL"
    elif multiple:
        name_status = "AMBIGUOUS"
    else:
        name_status = "NOT_FOUND" if any(s.field == "product_name_candidate" for s in signals) else "NO_TEXT"
    # Hàm lượng hiển thị: ưu tiên giá trị TRÙNG đơn (nhãn có nhiều con số, vd
    # bảng dinh dưỡng "0 g" ở anh_15), sau đó mới tới giá trị đầu tiên đọc được.
    trung_don = sorted(set(top["strength_expected"] or []) & set(hl_quan_sat)) if top else []
    so, dv = _don_vi((trung_don or hl_quan_sat or [None])[0])
    extracted = {
        "name": top["name"] if top and not partial else None,
        "strength": so,
        "unit": dv,
        "form": None,  # dạng bào chế công khai lấy từ VLM; OCR chỉ ở `ocr_forms`
    }
    return {
        "ocr_status": obs.status,
        "candidates": candidates[:5],
        "matched_prescription": (
            {"drug_id": top["drug_id"], "name": top["name"]} if top and not partial else None
        ),
        "mismatched_fields": mismatched,
        "extracted": extracted,
        "name_status": name_status,
        "ocr_forms": _dang_vien(obs.text),
        "rotation": goc,
        "multiple_candidates": multiple,
    }


def _ocr_rong(status: str, goc: int = 0) -> dict[str, Any]:
    """Cùng cấu trúc với kết quả có chữ — mọi nhánh trả đủ khoá."""
    return {"ocr_status": status, "candidates": [], "matched_prescription": None,
            "mismatched_fields": [], "extracted": None, "multiple_candidates": False,
            "name_status": "NO_TEXT" if status == OCR_AVAILABLE else None, "ocr_forms": [], "rotation": goc}


def ocr_khong_chay() -> dict[str, Any]:
    return _ocr_rong(OCR_NOT_RUN)


def xay_dung_ket_qua(
    *,
    ket_qua: str,
    confidence: str | None,
    expected_by_form: Mapping[str, int],
    detected_by_form: Mapping[str, int],
    evidence: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Tầng 5: hợp nhất thành object công khai. None khi còn dang_xu_ly.

    Dòng cũ (trước migration 0066) không có `evidence` -> vẫn suy được
    verification_result từ `ket_qua`, các trường OCR để rỗng.
    """
    if ket_qua == "dang_xu_ly":
        return None
    ev = dict(evidence or {})
    quality = ev.get("image_quality")
    ocr = ev.get("ocr") or {}
    lech_so = sorted(
        f"count:{k}" for k in set(expected_by_form) | set(detected_by_form)
        if int(expected_by_form.get(k, 0)) != int(detected_by_form.get(k, 0))
    )
    mismatched = list(ocr.get("mismatched_fields") or [])
    reason: str | None = None

    if ket_qua == "khop":
        result = MATCHED
    elif ket_qua == "lech":
        result = MISMATCHED
        mismatched = lech_so + mismatched
    elif ket_qua == "do_tin_cay_thap":
        result = UNCERTAIN
        reason = REASON_INSUFFICIENT_IMAGE if ev.get("rejected_by_quality") else REASON_UNCERTAIN
    elif ket_qua == "khong_xac_minh_duoc":
        result, reason = UNCERTAIN, REASON_UNKNOWN
    else:  # loi_he_thong hoặc giá trị lạ
        result, reason = UNCERTAIN, REASON_SYSTEM_ERROR
    if result == UNCERTAIN and reason == REASON_UNCERTAIN and ocr.get("multiple_candidates"):
        reason = REASON_MULTIPLE_CANDIDATES

    vlm_status = ev.get("vlm_status")
    if vlm_status is None and ket_qua in ("khop", "lech", "do_tin_cay_thap") and not ev.get("rejected_by_quality"):
        vlm_status = VLM_OK  # dong cu truoc khi co truong nay
    sources = [EVIDENCE_VLM_COUNT] if vlm_status == VLM_OK else []
    if quality and quality.get("status") != QUALITY_NOT_ASSESSED:
        sources.insert(0, EVIDENCE_QUALITY_GATE)
    if ocr.get("ocr_status") == OCR_AVAILABLE:
        sources.append(EVIDENCE_OCR)

    extracted = dict(ocr.get("extracted") or {"name": None, "strength": None, "unit": None, "form": None})
    forms = sorted(k for k, v in detected_by_form.items() if int(v) > 0)

    # Mâu thuẫn OCR <-> VLM trên trường có ý nghĩa lâm sàng. KHÔNG chọn bên
    # "tự tin hơn": giữ nguyên quyết định đã duyệt (bộ đếm VLM, ADR-0011) và
    # BÁO mâu thuẫn để người xem lại.
    #  - form: nhãn ghi "viên nén" mà VLM chỉ đếm được viên nang (hoặc ngược lại).
    #  - strength: hàm lượng đọc được khác đơn (từ tầng đối chiếu).
    conflicts: list[str] = []
    vien_vlm = {f for f in forms if f in _DANG_VIEN_OCR.values()}
    ocr_forms = set(ocr.get("ocr_forms") or [])
    if ocr_forms and vien_vlm and not (ocr_forms & vien_vlm):
        conflicts.append("form")
    if "strength" in (ocr.get("mismatched_fields") or []):
        conflicts.append("strength")
    extracted["form"] = forms[0] if len(forms) == 1 else (forms or None)

    return {
        "verification_result": result,
        "uncertainty_reason": reason,
        "extracted": extracted,
        "candidates": list(ocr.get("candidates") or []),
        "evidence_source": sources,
        "image_quality": quality,
        "ocr_status": ocr.get("ocr_status"),
        "matched_prescription": ocr.get("matched_prescription"),
        "mismatched_fields": mismatched,
        # OCR thấy hàm lượng/tên khác đơn trong khi bộ đếm báo khớp: ghi nhận để
        # người xem lại, KHÔNG đổi quyết định (xem docstring module).
        "ocr_conflict": result == MATCHED and bool(conflicts),
        "vlm_status": vlm_status,
        "ocr_vlm_conflicts": conflicts,
        "name_status": ocr.get("name_status"),
        "ocr_rotation": ocr.get("rotation"),
        "confidence": confidence,
        # Nhận diện ảnh KHÔNG chứng minh đã uống — UI phải nói rõ (BR-4.9).
        "proves_ingestion": False,
    }
