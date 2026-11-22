# TASK-CAPY-20: FE client + proxy companion-api

**Domain:** `frontend`, `companion`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

Kế hoạch: [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md); [`ADR-0016`](../adrs/0016-capybara-companion-domain.md).

## Kết quả thực hiện (2026-11-14)

- `frontend/src/lib/companion.ts` (`getCompanion`, `renameCompanion`, `ackCelebration`, `sendCompanionEvent`, `toCompanionState`); `frontend/src/app/api/companion/[...path]/route.ts` (proxy theo whitelist đường dẫn và method, trả 204 không kèm body).
- Tôn trọng `enabled` và `unavailable_reason`; không có đơn vị nội bộ. `api-contracts.md` §3b đã bổ sung mã 409 theo code thật.
- Kiểm chứng: `tsc --noEmit` (toàn project) sạch; smoke test trên trình duyệt thật với backend local: GET/ack/PATCH chạy đúng.

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Chưa chạy `npm run build` hay full suite.
