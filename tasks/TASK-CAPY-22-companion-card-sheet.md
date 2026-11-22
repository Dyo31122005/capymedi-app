# TASK-CAPY-22: CompanionCard + CompanionSheet

**Domain:** `frontend`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

Kế hoạch: [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md); [`ADR-0016`](../adrs/0016-capybara-companion-domain.md).

## Kết quả thực hiện (2026-11-14)

- `companion-card.tsx` (Capy 3D, tên và giai đoạn, % từ backend, hàng bữa ăn hôm nay có ⏳ cho liều đang chờ người thân, chạm để phản ứng, tạm dùng 2D khi có lớp phủ khác để tránh 2 WebGL context), `companion-sheet.tsx` (Capy lớn, 4 giai đoạn, đặt tên).
- `patient/page.tsx`: hiện thẻ Capy **chỉ khi** `GET /companion/me` trả `enabled`; ngược lại giữ nguyên khối quote cũ. Bỏ `capy_khoc` khỏi vòng xoay (`capy-quotes.ts`).
- Kiểm chứng trên trình duyệt (Chrome headless + SwiftShader): thẻ render `3d`, tiến độ 83% đúng với seed; sheet render `3d`.

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Chưa chạy `npm run build` hay full suite.
