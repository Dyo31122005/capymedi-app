# TASK-CAPY-02: ADR-0016, contracts và business rules cho Capybara Companion

**Domain:** `docs` (`companion`, `scheduling`, `reward`)
**Owner:** AI + reviewer Tech Lead/PM
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

## Mục tiêu (Goal)

Chốt bằng văn bản các quyết định kiến trúc và contract trước khi code (ADR-0003). Các quy tắc lâm sàng và kinh tế điểm được ghi dưới dạng **đề xuất chờ duyệt**, không có hiệu lực.

## Acceptance Criteria (AC)

- [x] [`adrs/0016-capybara-companion-domain.md`](../adrs/0016-capybara-companion-domain.md) (Proposed), có dòng trong [`adrs/README.md`](../adrs/README.md).
- [x] [`specs/domains.md`](../specs/domains.md): thêm domain `companion` và hai ranh giới dữ liệu mới.
- [x] [`specs/business-rules.md`](../specs/business-rules.md) §8: BR-8.1 đến BR-8.11 và các hằng số, đánh dấu PROPOSED, ghi rõ ai cần duyệt.
- [x] [`specs/api-contracts.md`](../specs/api-contracts.md): §3-P (`PATCH /doses/{id}` đề xuất), §3b `companion-api`, dòng lịch sử thay đổi.
- [x] File task P0: `TASK-CAPY-01` đến `TASK-CAPY-10`.
- [ ] Tech Lead + PM review; bác sĩ duyệt BR-8.2 (`LATE_REPORT_DAYS`); Tech Lead duyệt BR-8.7.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md) (R2)
- [ ] `AGENTS.md`, ADR-0002/0003/0004/0005

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Chỉ có tài liệu, không có code.

## Ghi chú / trao đổi thêm

- Phát hiện: bảng §3 của `api-contracts.md` ghi `POST /doses/{id}/confirm`, còn code thực tế dùng `PATCH /doses/{id}`. Mình ghi lại endpoint thực tế ở §3-P và không sửa dòng cũ.
- Quyết định mặc định cho các điểm chưa chốt (để code có hằng số): `LATE_REPORT_DAYS = 3`; ngưỡng 300/1400/4200; job đối soát 15 phút. Tất cả là hằng số có tên và **chưa có hiệu lực** cho tới khi được duyệt.
