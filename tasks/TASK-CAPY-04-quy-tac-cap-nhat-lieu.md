# TASK-CAPY-04: Hàm thuần `kiem_tra_cap_nhat_lieu` + `LATE_REPORT_DAYS`

**Domain:** `scheduling`
**Owner:** `[chờ phân công]` + AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

## Mục tiêu (Goal)

Trong `backend/services/dose_lifecycle.py`, thêm hàm thuần quyết định một PATCH là *cho phép / no-op / từ chối kèm lý do*, kèm cờ `cung_ngay` (BR-8.1 đến BR-8.3).

## Acceptance Criteria (AC)

- [ ] Unit test đủ ma trận whitelist BR-8.3 (theo role và quyền sở hữu liều), bao gồm ngoại lệ: duyệt `AWAITING_CAREGIVER` không giới hạn ngày.
- [ ] Gửi lại đúng trạng thái hiện tại trả *no-op*.
- [ ] `LATE_REPORT_DAYS` là hằng số có tên; biên `hôm nay − N` được tính theo ngày giờ Việt Nam (dùng `ngay_vn`).

## Phụ thuộc

TASK-CAPY-02 được duyệt (BR-8.2/8.3).

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md) (R2), mục liên quan
- [ ] [`adrs/0016-capybara-companion-domain.md`](../adrs/0016-capybara-companion-domain.md), [`specs/business-rules.md`](../specs/business-rules.md) §8
- [ ] `AGENTS.md`

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md), cộng checklist "an toàn và dữ liệu bệnh nhân".

## Kết quả thực hiện (2026-11-14)

- `backend/services/dose_lifecycle.py`: `kiem_tra_cap_nhat_lieu`, `QuyetDinhCapNhat`, `LATE_REPORT_DAYS = 3` (**PROVISIONAL**), `TRANG_THAI_DUOC_PATCH`, `TRANG_THAI_DA_BAO_CAO`.
- Khoảng báo cáo trễ (BR-8.2) chỉ áp dụng khi `settings.dose_provisional_policy_enabled` bật (**mặc định TẮT**).
- Test: `tests/services/test_dose_lifecycle_rules.py`, **xanh** (chạy chung lượt 49 test).
