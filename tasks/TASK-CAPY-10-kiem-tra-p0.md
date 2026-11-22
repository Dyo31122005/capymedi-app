# TASK-CAPY-10: Kiểm tra cuối P0

**Domain:** `qa`
**Owner:** `[chờ phân công]` + AI
**Sprint:** `[chưa xếp sprint]`
**Status:** Done (kiểm tra tập trung) — chưa chạy full suite

## Mục tiêu (Goal)

Chạy các bộ kiểm tra bắt buộc trước khi mở PR cho P0.

## Acceptance Criteria (AC)

- [ ] `pytest`, `ruff check .`, `npm run lint`, `npm run build` xanh, với **kết quả thật** được ghi lại.

## Phụ thuộc

TASK-CAPY-04 đến 09.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md) (R2), mục liên quan
- [ ] [`adrs/0016-capybara-companion-domain.md`](../adrs/0016-capybara-companion-domain.md), [`specs/business-rules.md`](../specs/business-rules.md) §8
- [ ] `AGENTS.md`

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md), cộng checklist "an toàn và dữ liệu bệnh nhân".

## Kết quả thực hiện (2026-11-14)

Theo chính sách test tập trung của PO, **không** chạy full `pytest`, `npm run lint` hay `npm run build`.

| Lệnh | Kết quả |
|---|---|
| `pytest tests/test_api/test_dose_status_rules.py` (baseline, trước khi sửa) | 7 failed: cả 7 lỗ hổng tái hiện được |
| `pytest tests/test_api/test_dose_status_rules.py` (sau khi sửa) | 7 passed |
| `pytest tests/services/test_dose_lifecycle_rules.py tests/test_dose_status_update.py tests/services/photo_verification/test_verifier.py` | 48 passed, 1 failed, rồi sau khi sửa test sai actor: 14/14 file dose status |
| `alembic upgrade/downgrade/upgrade` (0064) | OK |
| `ruff check` (10 file Python đã sửa) | All checks passed |

Môi trường: `.venv` Python 3.11 + Postgres 16 (pgvector) trong container riêng `capymedi-test-pg`, DB test bỏ đi được; `DATABASE_URL=postgresql+psycopg2://…` (xem ghi chú SQLAlchemy 2.1 ở TASK-CAPY-10).

**Phát hiện môi trường:** `requirements.txt` để `sqlalchemy>=2.0.0` không pin. Cài mới sẽ ra SQLAlchemy **2.1.8**, và bản này coi `postgresql://` là driver **psycopg 3**, trong khi repo chỉ cài `psycopg2-binary`. Lỗi gặp phải: `ModuleNotFoundError: psycopg` ngay khi chạy `alembic`. Rủi ro cho mọi lần cài mới (CI `golden-smoke`, build Docker production) nếu `DATABASE_URL` dùng `postgresql://`. **Chưa sửa** vì nằm ngoài phạm vi; cần Tech Lead quyết (pin `sqlalchemy<2.1` hoặc dùng `postgresql+psycopg2://`).
