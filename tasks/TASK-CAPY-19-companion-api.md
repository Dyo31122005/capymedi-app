# TASK-CAPY-19: companion-api

**Domain:** `companion`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

Kế hoạch: [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md); [`ADR-0016`](../adrs/0016-capybara-companion-domain.md).

## Kết quả thực hiện (2026-11-14)

- `backend/api/companion_routes.py`, `backend/models/companion_schemas.py`, đăng ký ở `backend/main.py`.
- `GET /api/v1/companion/me` (đọc thuần), `PATCH /api/v1/companion/me` (đặt tên), `POST /api/v1/companion/me/celebrations/{stage}/ack` (204, idempotent), `POST /api/v1/companion/me/events` (202, chỉ log). Chỉ role patient, `patient_id` lấy từ JWT. Route ghi trả **409** khi companion chưa bật cho bệnh nhân.
- **Bổ sung contract:** mã 409 cho route ghi chưa có trong `api-contracts.md` §3b, cần ghi thêm khi review.
- Test `tests/test_api/test_companion_routes.py`: GET khi tắt; 403 với người thân; GET không tạo dòng và không lộ đơn vị; đặt tên 200/422/409; ack 422/204/204; events 202/422. **Xanh.**
- Tổng các file test companion: **39 passed**.

Môi trường: `.venv` Python 3.11, SQLAlchemy 2.0.57, Postgres 16 (`capymedi-test-pg`), `DATABASE_URL=postgresql://…`.

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Chưa chạy full suite; job CI `lint-and-test` skip các test cần Postgres.
