# TASK-CAPY-27 — Khôi phục luồng xác nhận bằng ảnh (photo-first) + kết quả xác minh có cấu trúc

| Trường | Giá trị |
|---|---|
| Domain | `photo-verification`, `companion` (FEED/SUPPORTIVE) |
| Người làm | AI (cần Tech Lead review) |
| Trạng thái | 🔎 In Review |
| Liên quan | ADR-0011, ADR-0004 §10, BR-4.4–4.6, api-contracts.md §5, TASK-CAPY-26 (QA-03) |

## Mục tiêu
"Chụp ảnh xác nhận" là nút chính trên thẻ liều; tự xác nhận không ảnh nằm trong "Tùy chọn khác".
Pipeline ảnh tách tầng: chất lượng → OCR → thực thể → đối chiếu đơn → quyết định → bệnh nhân tự xác nhận.

## Nguyên nhân camera "biến mất" (không phải regression code)
1. `patient/page.tsx` (HEAD): `khongCanAnh = !chupAnhBat || trangThai === "overdue" || trangThai === "waiting"` —
   liều quá giờ/đã hoãn tự chuyển nút chính thành "Tôi đã uống".
2. Seed demo local đặt `photo_capture_enabled=False` (tài khoản demo, không phải production).

## Acceptance Criteria
- [x] AC1 Nút chính "Chụp ảnh xác nhận" (icon camera) ở mọi trạng thái liều khi bệnh nhân chưa tắt chụp ảnh trong Cài đặt.
- [x] AC2 "Tùy chọn khác": "Tôi không thể chụp ảnh — xác nhận thủ công", "Xem hướng dẫn chụp ảnh".
- [x] AC3 Camera: xem trước, chụp lại, huỷ, tải ảnh lên; từ chối quyền camera → tải ảnh lên (vẫn qua xem trước).
- [x] AC4 Câu hướng dẫn "Chụp rõ tên thuốc, hàm lượng hoặc vỉ thuốc."; ảnh không đạt → "Chưa đọc rõ thông tin thuốc…".
- [x] AC5 Nút gửi "Gửi ảnh & xác nhận đã uống" + câu nói rõ ảnh không chứng minh đã uống (BR-4.4).
- [x] AC6 API trả `verification` (MATCHED/MISMATCHED/UNCERTAIN + lý do + trường trích xuất) — additive.
- [x] AC7 OCR tên/hàm lượng chỉ tư vấn, sau cờ `photo_ocr_evidence_enabled` (mặc định TẮT); không đổi `ket_qua`/status/điểm.
- [x] AC8 Ảnh khớp → Capy FEED; ảnh không khớp/hết lượt → SUPPORTIVE (giữ nguyên logic TASK-CAPY-17/26).

## Chưa làm / cần quyết định (không tự quyết)
- "Nhờ người thân hỗ trợ": chưa có API bệnh nhân chủ động nhờ người thân → không thêm nút (cần spec).
- Luồng 2 bước (kết quả ảnh → "Xác nhận đã uống liều này"): cần đổi ADR-0011 (khớp → TAKEN ngay). Hiện dùng
  phương án 1 bước có cam kết rõ ràng (PO cho phép).
- Mâu thuẫn chính sách: hết 3 lần ảnh lệch + không có người thân → backend vẫn tự chốt `TAKEN` (70% LP) mà
  bệnh nhân chưa tự xác nhận lần nữa. Companion đã loại liều này khỏi tăng trưởng (QA-03), nhưng hồ sơ lâm sàng
  vẫn ghi TAKEN. Cần PM + bác sĩ chốt.
- Bật OCR làm tín hiệu quyết định: cần eval trên ảnh viên thuốc rời (ADR-0004 §10).

## Kiểm thử
- `tests/services/photo_verification/test_evidence.py` (16, thuần) + 3 test mới trong `test_verifier.py` (Postgres).
- Smoke trình duyệt (camera giả của Chrome + VLM giả lập, DB local): 14/14 kiểm tra PASS.
- VLM/OCR thật: **UNVERIFIED** (không có khóa VLM được cấp; Tesseract không cài local).
