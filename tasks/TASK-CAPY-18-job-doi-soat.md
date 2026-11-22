# TASK-CAPY-18: Job đối soát companion

**Domain:** `companion`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

Kế hoạch: [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md); [`ADR-0016`](../adrs/0016-capybara-companion-domain.md).

## Kết quả thực hiện (2026-11-14)

- `companion.service.doi_soat_gan_day` cùng `ThongKeDoiSoat`; đăng ký `_run_companion_reconcile` (interval `companion_reconcile_minutes`, `max_instances=1`) trong `escalation_scheduler.py`.
- Nguồn ứng viên: (1) `first_reported_at` trong cửa sổ → hôm qua + hôm nay; (2) đã có `companion_care_day` trong cửa sổ → hôm qua + hôm nay; (3) **vết audit `DOSE_STATUS_CHANGE`** trong cửa sổ → **chính ngày hẹn** của liều (`slot_summary.cap_benh_nhan_ngay_doi_trang_thai_tu`).
- **Ca biên D / D+5:** cửa sổ 2 ngày một mình **không** bắt được ngày D. Nguồn (3) bắt được vì audit được ghi cùng transaction với status, nằm ngoài savepoint của companion, nên vẫn còn khi hook lỗi. **Đã kiểm chứng bằng test** `test_nguoi_than_duyet_ngay_d_cong_5_hook_loi_job_van_phuc_hoi`.
- **Giới hạn còn lại:** job ngừng chạy lâu hơn `companion_reconcile_lookback_days` (2 ngày) thì vết audit cũ rơi ngoài cửa sổ, cần CLI đối soát (TASK-CAPY-32). Lần đầu bật flag sẽ có WARNING `recovered_missing` cho các xác nhận ≤ 2 ngày trước khi bật (backfill có giới hạn, như đã dự kiến).
- Log: WARNING JSON `companion_recovered_missing` (`patient_id`, `care_date`); INFO JSON tổng kết; không có PHI.
- Test `tests/services/test_companion_reconcile.py`: phục hồi khi hook bỏ lỡ và chạy lại không đổi gì; huỷ liều giữa ngày (`schedule_adjusted`); cờ tắt hoặc v2 thì bỏ qua; không quét lịch sử cũ; một bệnh nhân lỗi không chặn bệnh nhân khác; D / D+5. **Xanh.**

Môi trường: `.venv` Python 3.11, SQLAlchemy 2.0.57, Postgres 16 (`capymedi-test-pg`), `DATABASE_URL=postgresql://…`.

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Chưa chạy full suite; job CI `lint-and-test` skip các test cần Postgres.
