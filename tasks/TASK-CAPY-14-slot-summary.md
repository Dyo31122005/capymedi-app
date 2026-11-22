# TASK-CAPY-14: `scheduling.slot_summary` (legacy/shadow)

**Domain:** `scheduling`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

Kế hoạch: [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md) §4 và §5; [`ADR-0016`](../adrs/0016-capybara-companion-domain.md).

## Kết quả thực hiện (2026-11-14)

- `backend/services/scheduling/slot_summary.py`: `SlotFact`, `liet_ke_slot_ngay`, `benh_nhan_co_bao_cao_tu`, `runtime_ho_tro`, `RuntimeKhongHoTroError` (mode `v2`).
- Ngày VN qua `reward_ledger.ngay_vn`, cùng định nghĩa với điểm thưởng và job chốt MISSED. Lọc SQL theo khoảng ±1 ngày rồi chốt ngày trong Python.
- Test (Postgres): liều 06:00 VN (23:00 UTC hôm trước) thuộc đúng ngày; giữ CANCELLED để nơi gọi tự loại; bỏ liều ngày khác; v2 raise. **Xanh.**
- `benh_nhan_co_bao_cao_tu` (cho job TASK-CAPY-18) đã có code nhưng **chưa có test riêng**; test cùng job.

Môi trường: `.venv` Python 3.11, SQLAlchemy 2.0.57, Postgres 16 (`capymedi-test-pg`), `DATABASE_URL=postgresql://…` (URL gốc, sau khi sửa B-5).

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Chưa chạy full suite; job CI `lint-and-test` skip các test cần Postgres.
