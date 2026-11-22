# TASK-CAPY-15: `companion.service` — `tinh_lai_ngay` + đọc trạng thái

**Domain:** `companion`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

Kế hoạch: [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md) §4 và §5; [`ADR-0016`](../adrs/0016-capybara-companion-domain.md).

## Kết quả thực hiện (2026-11-14)

- `backend/services/companion/service.py`: `tinh_lai_ngay` (tạo dòng an toàn bằng savepoint, `FOR UPDATE`, flush, đếm, `GREATEST`, không commit), `tong_growth`, `lay_trang_thai` (đọc thuần), `xac_nhan_da_mung` (idempotent), `dat_ten`; `errors.py`.
- `backend/config.py`: `companion_enabled = False`. **Lệch nhỏ:** cờ này dự kiến ở TASK-CAPY-16, nhưng `lay_trang_thai` cần nó để trả `FEATURE_OFF`. Cohort và allowlist vẫn để TASK-16.
- Test (Postgres): ngày không liều không tạo dòng; gọi 10 lần cho cùng kết quả; hàng 5b (dừng phác đồ giữa ngày, 50 → 100); 7b (liều tương lai bị xoá, 50 → 100); 7a và 14 (chỉ tăng); 8 (báo cáo trễ = 0); 11a/11b (AWAITING chỉ tính khi duyệt TAKEN); GET không tạo dòng và không lộ đơn vị nội bộ; flag tắt thì `FEATURE_OFF`; ack idempotent và chặn giai đoạn chưa đạt.
- **Test khoá Postgres:** A giữ `FOR UPDATE` chưa commit; B (thread khác) **bị chặn** (đã assert), và sau khi A commit thì B tính ra 100. Không có khoá thì kết quả sẽ là 50. **Xanh.**
- Tổng cộng: `test_companion_progression.py` và `test_companion_service.py`: **35 passed**. `ruff`: pass.

Môi trường: `.venv` Python 3.11, SQLAlchemy 2.0.57, Postgres 16 (`capymedi-test-pg`), `DATABASE_URL=postgresql://…` (URL gốc, sau khi sửa B-5).

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Chưa chạy full suite; job CI `lint-and-test` skip các test cần Postgres.
