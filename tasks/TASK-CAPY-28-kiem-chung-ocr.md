# TASK-CAPY-28 — Kiểm chứng, bật local và cải thiện OCR bằng chứng tên/hàm lượng

| Trường | Giá trị |
|---|---|
| Domain | `photo-verification` |
| Người làm | AI (cần Tech Lead review) |
| Trạng thái | 🔎 In Review |
| Liên quan | TASK-CAPY-27, ADR-0011, ADR-0004 §10, BR-4.4–4.6, api-contracts.md §5 |

## Kết quả
- Tesseract 5.3.4 thật chạy local (vie/eng/osd); OCR bật **chỉ ở local** bằng env
  `PHOTO_OCR_EVIDENCE_ENABLED=true` — mặc định trong `backend/config.py` vẫn `False`.
- Eval: [`eval/eval_ocr/eval_report.md`](../eval/eval_ocr/eval_report.md).
- Sửa (đều có bằng chứng quan sát được): đơn vị IU; không kết luận lệch tên khi chỉ "không thấy";
  token tên chữ+số (D3) + khớp một phần = `PARTIAL`; ưu tiên hàm lượng trùng đơn khi hiển thị;
  thử xoay 90/270 khi 0° gần như không có chữ; báo mâu thuẫn OCR↔VLM (`ocr_vlm_conflicts`).
- OCR vẫn ở chế độ bằng chứng: không đổi `ket_qua`, trạng thái liều, LP/SP, tăng trưởng Capy.

## Bật OCR ở máy dev
```bash
# Tesseract + vie/eng phải có trên PATH (vd giải nén .deb vào ~/tools/tesseract, xem eval_report)
export PHOTO_OCR_EVIDENCE_ENABLED=true
```

## Cần quyết định (không tự làm)
- Khi OCR↔VLM mâu thuẫn (vd nhãn "0.5 mg" + "viên nang" nhưng VLM đếm khớp viên nén) liều vẫn chốt
  TAKEN theo ADR-0011, mâu thuẫn chỉ được lưu/trả về — chưa ai được báo. Có chuyển sang UNCERTAIN/
  người xem lại hay không: cần PM + bác sĩ.
- Bật OCR ở staging/production: cần eval trên ảnh vỉ/hộp thuốc kê đơn thật (có phép).
