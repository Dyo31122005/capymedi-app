# Eval OCR bằng chứng tên/hàm lượng — 2026-11-14 (TASK-CAPY-28)

**Phạm vi:** OCR chỉ là bằng chứng TƯ VẤN (`photo_ocr_evidence_enabled`, mặc định TẮT). Đây là
kiểm chứng engine + parse và đánh giá **sơ bộ**, KHÔNG phải thẩm định lâm sàng.

- Engine: Tesseract 5.3.4 (leptonica 1.82.0), ngôn ngữ `vie+eng` (+`osd`), giải nén local từ
  gói Ubuntu noble (không cài hệ thống). Production Dockerfile cài `tesseract-ocr`, `-eng`, `-vie`.
- Đường code: `nen_anh` → `evidence.trich_xuat_va_doi_chieu` (adapter `OptionalTesseractOcrExtractor`
  có sẵn, 2 lượt màu + xám) — chạy lại: `python eval/eval_ocr/run_eval_ocr.py`.

## A. Nhãn tổng hợp (12 ca × 2 cỡ chữ = 24 lần chạy, ground truth biết trước)

| | Trước sửa | Sau sửa |
|---|---|---|
| Đúng kỳ vọng (strength_match + name_status) | 20/24 | **24/24** |
| 0.5 mg vs 5 mg, "0,5 mg", 50 vs 500 mg, 50 mcg vs 50 mg, 2 hoạt chất | phát hiện đúng | phát hiện đúng |
| "1000 IU" | bỏ qua (thiếu đơn vị IU) | đọc + so đúng |
| Biệt dược "PANADOL" vs đơn "Paracetamol" | gắn nhầm `mismatched_fields=["name"]` | `NOT_FOUND`, không kết luận lệch |
| "50 µg" | Tesseract đọc thành "Hg"/"ng" → không trích | giữ nguyên: **không đoán** ("ng" là đơn vị thật) |

## B. Ảnh golden set `eval/eval_vlm/anh_test` (25 ảnh team tự chụp, không phải ảnh bệnh nhân)

Ground truth tên/hàm lượng ghi tay. Chỉ 5/25 ảnh có nhãn đọc được bằng mắt; 20 ảnh là viên thuốc rời.

| Ảnh | Ground truth | Tên | Hàm lượng | Ghi chú |
|---|---|---|---|---|
| anh_5 | Pharmaton Kiddi (siro) | không đọc được | — | ảnh nhỏ 600×530; phóng to cũng không đọc được |
| anh_6 | Adacine, tuýp 15 g (chữ dọc) | không đọc được | **15 g** (chỉ sau khi xoay 270°) | trước sửa: chỉ ra rác |
| anh_14 | Vitamin C 500 mg (+ chai kẹo Xylatol 500 mg) | đúng | 500 mg đúng | `ocr_forms=vien_nen` đến từ nhãn chai kẹo |
| anh_15 | Vitamin D3 1000 IU (+ bảng dinh dưỡng) | đúng | 1000 IU đúng | trước sửa: hiển thị "0 g" từ bảng dinh dưỡng |
| anh_19 | Smecta, Diosmectite 3 g | đúng (Smecta) | **không đọc được** "3 g" | chữ nhỏ 381×486 |
| 20 ảnh viên rời | không có nhãn | 19 `NO_TEXT`, 1 `NOT_FOUND` (chữ rác) | không trích sai | 0 dương tính giả |

Lỗi nhận nhầm phát hiện trên ảnh thật và đã sửa: đơn **"Vitamin D3"** trên anh_14 (chai Vitamin C)
từng khớp tên 100% vì token "d3" bị loại → nay `PARTIAL`, không gán `matched_prescription`.

## Thử và KHÔNG áp dụng (không chứng minh được lợi ích)
- **OSD của Tesseract** để tự xoay: trả hướng SAI trên anh_6 (conf 0.64) → thay bằng thử 90/270 khi 0° gần như không có chữ.
- **Phóng to ảnh nhỏ**: anh_19 đọc thêm tên hoạt chất nhưng méo ("Dicarnecti#te"), "3 g" thành "3q"/"30."; anh_6 ra rác.
- **So hàm lượng chỉ trong cùng nhóm đơn vị**: sẽ làm mất tín hiệu đúng "500 mg ≠ 1000 IU" trên anh_14.

## Hạn chế
- Mẫu ảnh thật rất nhỏ (5 ảnh có nhãn) → kết quả **sơ bộ**, chưa đủ để tính độ chính xác.
- Chưa có ảnh vỉ thuốc/hộp thuốc kê đơn thật với tên hoạt chất + hàm lượng rõ.
- Dạng bào chế chỉ nhận "viên nén"/"viên nang" từ chữ trên nhãn; dạng khác lấy từ VLM.
- Nhãn có nhiều con số (bảng dinh dưỡng, "Hộp 10 vỉ") vẫn có thể sinh hàm lượng nhiễu.
- Biệt dược ↔ hoạt chất cần bảng ánh xạ từ catalog — chưa làm (không fuzzy match).
- Chi phí: +~1 s/ảnh khi ảnh không có chữ (3 lần chấm điểm xoay), chạy ở background task.
