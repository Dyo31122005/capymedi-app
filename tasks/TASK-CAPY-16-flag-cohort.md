# TASK-CAPY-16: Feature flag, cohort, allowlist, runtime

**Domain:** `companion`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

Kế hoạch: [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md); [`ADR-0016`](../adrs/0016-capybara-companion-domain.md).

## Kết quả thực hiện (2026-11-14)

- `backend/config.py`: `companion_enabled=False`, `companion_rollout_percentage=0`, `companion_allowlist=""`, `companion_reconcile_minutes=15`, `companion_reconcile_lookback_days=2`.
- `companion/service.py`: `companion_bat_cho`, `ly_do_khong_kha_dung`, `_trong_cohort` (bucket `sha256(patient_id) % 100`, cùng cách với `agent_v2_routes._in_rollout_percentage`). Ngoài cohort cũng trả `FEATURE_OFF`, để không lộ thông tin cohort.
- Test `tests/services/test_companion_flag.py`: mặc định tắt; bật cờ nhưng pct=0 và allowlist rỗng thì vẫn tắt; allowlist; cohort ổn định và tăng pct không đẩy ai ra; `legacy`/`shadow` bật, `v2` trả `RUNTIME_UNSUPPORTED`. **Xanh.**

Môi trường: `.venv` Python 3.11, SQLAlchemy 2.0.57, Postgres 16 (`capymedi-test-pg`), `DATABASE_URL=postgresql://…`.

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Chưa chạy full suite; job CI `lint-and-test` skip các test cần Postgres.
