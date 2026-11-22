# TASK-V2.6-001: Chatbot Agent V2 sẵn sàng demo (sửa review #9, ngữ cảnh đơn thuốc, lọc theo buổi)

**Domain:** Agent V2 (orchestrator, runtime, read-only tools)
**Owner:** MustelaFerret + AI
**Branch:** `fix/agent-v2-review-issue-9` (từ `main` sau PR #8)
**Quyết định kiến trúc liên quan:** ADR-0017
**Status:** In progress

## Mục tiêu

Đưa chatbot về trạng thái demo được cho pitching: các luồng chính trả lời đúng, tự nhiên, dựa trên dữ liệu thật của người bệnh, và lớp an toàn không yếu hơn `main`.

## Acceptance Criteria

**A. Sửa review issue #9**
- [x] Lỗi chặn 1–3: câu tự hại, bé uống thuốc, "buồn/đau muốn chết" đều chuyển khẩn cấp khi bộ phân loại ngữ nghĩa tắt (có test cho cả bản có dấu và không dấu).
- [x] Lỗi chặn 4: cache web không thể trả câu trả lời của bệnh nhân này cho bệnh nhân khác.
- [x] Lỗi chặn 5: lời khẩn cấp chưa duyệt lâm sàng nằm sau cờ `AGENT_SAFETY_B3_ENABLED` (mặc định tắt, dùng văn bản của main).
- [x] Mục 6–11 của review.
- [x] Mục 🟠 được chốt trong ADR-0017.

**B. Ngữ cảnh đơn thuốc của người bệnh**
- [x] "Đơn thuốc của tôi gồm những gì?" liệt kê đúng từng thuốc: tên, liều, thời điểm so với bữa ăn, giờ nhắc, ngày kết thúc.
- [x] Hỏi về một thuốc có trong đơn thì tra tờ hướng dẫn của **đúng sản phẩm trong đơn** (vd Metformin 500mg Stella, không phải loại 1000mg).
- [x] Kể một triệu chứng mà tờ hướng dẫn của thuốc trong đơn có ghi là tác dụng phụ thì câu trả lời nhắc điều đó, và vẫn giữ nguyên các dấu hiệu nguy hiểm, 115.

**C. Lọc lịch theo buổi**
- [x] "Tối nay / sáng mai / trưa nay… uống thuốc gì?" chỉ liệt kê các cữ thuộc buổi đó.

## Definition of Done

- Test hồi quy cho từng AC; toàn bộ test không có lỗi mới so với `main`.
- `ruff check backend/ tests/` sạch.
- Kiểm tra trực tiếp trên tài khoản test BN00015 qua API thật.
