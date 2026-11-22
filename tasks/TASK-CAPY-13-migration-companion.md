# TASK-CAPY-13: Model + migration `0065_companion`

**Domain:** `companion`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

Kế hoạch: [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md) §4 và §5; [`ADR-0016`](../adrs/0016-capybara-companion-domain.md).

## Kết quả thực hiện (2026-11-14)

- `Companion`, `CompanionCareDay` trong `backend/db/models.py`; `migrations/versions/0065_companion.py`.
- **Đã kiểm chứng trên Postgres:** upgrade → downgrade → upgrade sạch; có `ck_companion_care_day_units` và PK `(patient_id, care_date)`.
- Lệch nhỏ so với kế hoạch: dùng `Integer` thay `SMALLINT` (theo convention các bảng hiện có).

Môi trường: `.venv` Python 3.11, SQLAlchemy 2.0.57, Postgres 16 (`capymedi-test-pg`), `DATABASE_URL=postgresql://…` (URL gốc, sau khi sửa B-5).

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Chưa chạy full suite; job CI `lint-and-test` skip các test cần Postgres.
