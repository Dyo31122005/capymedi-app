# TASK-CAPY-07: `danh_dau_da_bao_cao`: ghi `first_reported_at`

**Domain:** `scheduling`, `photo-verification`
**Owner:** `[chờ phân công]` + AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

## Mục tiêu (Goal)

Ghi `first_reported_at` đúng một lần khi liều chuyển vào `TAKEN`/`DELAYED`/`AWAITING_CAREGIVER`, ở PATCH và ở ba nhánh verifier (`verifier.py:318`, `:354`, `:362`).

## Acceptance Criteria (AC)

- [ ] Ghi đúng một lần; không ghi đè khi đi `TAKEN→MISSED→TAKEN`.
- [ ] `AWAITING_CAREGIVER` có ghi; `MISSED` không ghi.

## Phụ thuộc

TASK-CAPY-06.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md) (R2), mục liên quan
- [ ] [`adrs/0016-capybara-companion-domain.md`](../adrs/0016-capybara-companion-domain.md), [`specs/business-rules.md`](../specs/business-rules.md) §8
- [ ] `AGENTS.md`

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md), cộng checklist "an toàn và dữ liệu bệnh nhân".

## Kết quả thực hiện (2026-11-14)

- `danh_dau_da_bao_cao`, `bao_cao_cung_ngay` trong `dose_lifecycle.py`. Được gọi ở PATCH và ở 3 nhánh verifier (khớp ảnh, AWAITING_CAREGIVER, TAKEN khi không có người thân).
- Test unit: ghi đúng một lần, không ghi đè khi đi TAKEN→MISSED→TAKEN, MISSED không ghi, AWAITING có ghi. **Xanh.** `tests/services/photo_verification/test_verifier.py` vẫn **xanh**.
