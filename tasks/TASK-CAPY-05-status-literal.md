# TASK-CAPY-05: `DoseStatusUpdateRequest.status` thành `Literal["TAKEN","MISSED"]`

**Domain:** `scheduling`
**Owner:** `[chờ phân công]` + AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

## Mục tiêu (Goal)

Chặn V-1 ngay ở tầng validation (BR-8.1).

## Acceptance Criteria (AC)

- [ ] Status ngoài `TAKEN`/`MISSED` trả 422.
- [ ] Các test V-1 và V-2 của TASK-CAPY-03 chuyển xanh.

## Phụ thuộc

TASK-CAPY-03.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md) (R2), mục liên quan
- [ ] [`adrs/0016-capybara-companion-domain.md`](../adrs/0016-capybara-companion-domain.md), [`specs/business-rules.md`](../specs/business-rules.md) §8
- [ ] `AGENTS.md`

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md), cộng checklist "an toàn và dữ liệu bệnh nhân".

## Kết quả thực hiện (2026-11-14)

- `DoseStatusUpdateRequest.status: Literal["TAKEN","MISSED"]`.
- Test V-1, V-2 **xanh** trên Postgres thật.
- Lưu ý: nhánh `dose_runtime_mode=v2` cũng dùng schema này, nên không còn gửi được `DELAYED`/`SKIPPED` qua PATCH. Frontend không gửi hai giá trị đó.
