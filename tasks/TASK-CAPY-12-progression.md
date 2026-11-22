# TASK-CAPY-12: Thuật toán "Ngày chăm sóc" (hàm thuần)

**Domain:** `companion`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

Kế hoạch: [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md) §4 và §5; [`ADR-0016`](../adrs/0016-capybara-companion-domain.md).

## Kết quả thực hiện (2026-11-14)

- `backend/services/companion/progression.py`: `eligible`, `growth_done`, `dem_ngay`, `day_units`, `stage_for`, `progress_pct`; hằng số `DAY_UNITS=100`, `STAGE_THRESHOLDS=(0,300,1400,4200)` (**giả thuyết, chờ PO duyệt D-5**).
- `tests/services/test_companion_progression.py`: tổ hợp status × ngày báo cáo, biên ngưỡng 299/300/1399/1400/4199/4200, các hàng 1, 2, 2b, 2c, 4a, 4b của §4.5. **Xanh.**
- Ghi chú B-5: đã pin `sqlalchemy>=2.0.0,<2.1` trong `requirements.txt`. Kiểm chứng: cài lại theo ràng buộc mới (ra 2.0.57), `alembic current` chạy được với URL `postgresql://` gốc.

Môi trường: `.venv` Python 3.11, SQLAlchemy 2.0.57, Postgres 16 (`capymedi-test-pg`), `DATABASE_URL=postgresql://…` (URL gốc, sau khi sửa B-5).

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Chưa chạy full suite; job CI `lint-and-test` skip các test cần Postgres.
