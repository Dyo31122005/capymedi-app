# TASK-CAPY-06: Migration `0064`: `dose_event.first_reported_at`

**Domain:** `scheduling`
**Owner:** `[chờ phân công]` + AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

## Mục tiêu (Goal)

Thêm cột nullable `first_reported_at` cùng partial index `WHERE first_reported_at IS NOT NULL`. Model khai báo cả `postgresql_where` lẫn `sqlite_where`. Không backfill (BR-8.5).

## Acceptance Criteria (AC)

- [ ] Trên Postgres: upgrade, downgrade, upgrade lại đều sạch.
- [ ] Không đổi schema `DoseSummary`.

## Phụ thuộc

TASK-CAPY-02.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md) (R2), mục liên quan
- [ ] [`adrs/0016-capybara-companion-domain.md`](../adrs/0016-capybara-companion-domain.md), [`specs/business-rules.md`](../specs/business-rules.md) §8
- [ ] `AGENTS.md`

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md), cộng checklist "an toàn và dữ liệu bệnh nhân".

## Kết quả thực hiện (2026-11-14)

- `migrations/versions/0064_dose_event_first_reported_at.py`, cột trong `DoseEvent` cùng partial index (khai báo `postgresql_where` và `sqlite_where`).
- **Đã kiểm chứng** trên DB test: upgrade → downgrade → upgrade sạch; cột `timestamptz NULL`; index `WHERE first_reported_at IS NOT NULL`. Môi trường: `.venv` Python 3.11 + Postgres 16 (pgvector) trong container riêng `capymedi-test-pg`, DB test bỏ đi được; `DATABASE_URL=postgresql+psycopg2://…` (xem ghi chú SQLAlchemy 2.1 ở TASK-CAPY-10).
