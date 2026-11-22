# TASK-CAPY-08: Nối quy tắc vào `PATCH /doses/{id}` + LP/SP + audit

**Domain:** `scheduling`, `reward`, `audit`
**Owner:** `[chờ phân công]` + AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review — chờ duyệt BR-8.2/BR-8.7a trước khi bật flag

## Mục tiêu (Goal)

Gọi `kiem_tra_cap_nhat_lieu` trong `update_dose_status` (nhánh legacy). No-op trả 200 mà không ghi gì. Báo cáo khác ngày thì không gọi `_thuong_diem_neu_uong_du` (BR-8.7). Mức trừ tự khai theo người gọi. Ghi `log_action` khi có thay đổi (BR-8.6).

## Acceptance Criteria (AC)

- [ ] Toàn bộ `tests/test_api/test_dose_status_rules.py` (TASK-CAPY-03) xanh.
- [ ] `tests/test_reward_ledger.py` vẫn xanh.
- [ ] Người thân duyệt `AWAITING_CAREGIVER` vẫn hoạt động.

## Phụ thuộc

TASK-CAPY-04, 05, 07. **BR-8.2 và BR-8.7 phải được duyệt trước khi merge.**

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md) (R2), mục liên quan
- [ ] [`adrs/0016-capybara-companion-domain.md`](../adrs/0016-capybara-companion-domain.md), [`specs/business-rules.md`](../specs/business-rules.md) §8
- [ ] `AGENTS.md`

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md), cộng checklist "an toàn và dữ liệu bệnh nhân".

## Kết quả thực hiện (2026-11-14)

- `update_dose_status`: quy tắc từ service; no-op trả 200 mà không ghi gì; `first_reported_at`; audit `DOSE_STATUS_CHANGE …` qua `log_action`.
- **Sửa V-3 (đã xác nhận bằng test):** bấm "Bỏ qua liều này" không còn bị ghi phạt −10 SP; mức trừ tự khai xét theo người gọi (`_xac_dinh_ty_le_thuong(da_uong=…)`).
- **PROVISIONAL, mặc định TẮT** (`dose_provisional_policy_enabled`): báo cáo khác ngày hẹn nhận 0 LP/SP (BR-8.7a), khoảng `LATE_REPORT_DAYS` (BR-8.2).
- **Thay đổi hành vi không nằm sau flag** (Tech Lead cần review): status chỉ nhận TAKEN/MISSED; bệnh nhân không tự duyệt được liều AWAITING_CAREGIVER của mình; MISSED→TAKEN do bệnh nhân tự khai giờ bị trừ như tự khai (trước đây giữ 100%).
- Test: `tests/test_api/test_dose_status_rules.py` **7/7 xanh**. `tests/test_dose_status_update.py` **14/14 xanh**, sau khi sửa một test vốn dùng token của chính bệnh nhân để "người thân duyệt" (trái docstring của nó).
