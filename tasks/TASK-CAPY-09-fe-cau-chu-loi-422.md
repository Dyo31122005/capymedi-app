# TASK-CAPY-09: FE: câu chữ tự khai + hiển thị lỗi 422

**Domain:** `frontend`
**Owner:** `[chờ phân công]` + AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

## Mục tiêu (Goal)

Sửa toast "điểm thấp hơn" (`frontend/src/app/patient/page.tsx:338`) và câu lỗi thời (`:684`); hiển thị `detail` của lỗi 422 thành toast thân thiện.

## Acceptance Criteria (AC)

- [ ] Không còn câu "người thân sẽ xác nhận giúp trước khi tính là đã uống".
- [ ] Lỗi 422 hiện đúng thông điệp do backend trả về.

## Phụ thuộc

TASK-CAPY-08.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md) (R2), mục liên quan
- [ ] [`adrs/0016-capybara-companion-domain.md`](../adrs/0016-capybara-companion-domain.md), [`specs/business-rules.md`](../specs/business-rules.md) §8
- [ ] `AGENTS.md`

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md), cộng checklist "an toàn và dữ liệu bệnh nhân".

## Kết quả thực hiện (2026-11-14)

- `frontend/src/app/patient/page.tsx`: toast tự khai thành "Đã ghi nhận bạn uống thuốc. Cảm ơn bạn!"; sheet xác nhận không ảnh báo trước "điểm thưởng sẽ thấp hơn một chút", thay câu lỗi thời về người thân.
- Lỗi 422: không cần sửa. `loi()` trong `lib/doses.ts` đã hiện `detail` dạng chuỗi thành toast.
- **Chưa lint** (máy không có `node_modules`); chỉ đổi 2 chuỗi text.
