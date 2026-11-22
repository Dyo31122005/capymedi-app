# TASK-CAPY-17: Nối companion vào xác nhận liều

**Domain:** `companion`, `scheduling`, `photo-verification`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

Kế hoạch: [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md); [`ADR-0016`](../adrs/0016-capybara-companion-domain.md).

## Kết quả thực hiện (2026-11-14)

- `companion.service.ghi_nhan_tu_hook`: chỉ chạy khi `companion_bat_cho`; `db.flush()` rồi `begin_nested()` (savepoint); khi lỗi thì `logger.exception("companion_hook_failed patient_id=… dose_id=…")` và xác nhận liều vẫn commit. Tính lại **ngày hẹn** của liều qua `tinh_lai_ngay`.
- Gắn ở `dose_routes.update_dose_status` (sau audit, trước commit; gồm cả đường người thân/bác sĩ) và ở `verifier` (trước commit, khi status ∈ TAKEN/DELAYED/AWAITING_CAREGIVER). Không gắn ở nhánh V2.
- Test (Postgres): PATCH TAKEN làm Capy lớn, retry không cộng đôi; cờ tắt thì không ghi gì; hook lỗi thì PATCH vẫn 200, status, `first_reported_at` và audit đều còn; AWAITING chỉ lớn khi người thân duyệt; verifier khớp ảnh thì 100; verifier ra AWAITING thì 0. **Xanh.** Các test có sẵn bị ảnh hưởng (`test_verifier.py`, `test_dose_status_rules.py`, `test_dose_status_update.py`): **44 passed**.

Môi trường: `.venv` Python 3.11, SQLAlchemy 2.0.57, Postgres 16 (`capymedi-test-pg`), `DATABASE_URL=postgresql://…`.

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Chưa chạy full suite; job CI `lint-and-test` skip các test cần Postgres.
