# TASK-CAPY-23: CareMoment: cho ăn / hỗ trợ / lớn lên

**Domain:** `frontend`, `companion`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

Kế hoạch: [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md); [`ADR-0016`](../adrs/0016-capybara-companion-domain.md).

## Kết quả thực hiện (2026-11-14)

- `src/lib/care-moment.ts` (`chonLoaiManHinh`: FEED/SUPPORTIVE/NEUTRAL theo **trạng thái liều do backend trả về**, không suy từ HTTP 200; `monAnTheoBuoi`; `fedSlotIds`), `care-moment.tsx` (FEED: món ăn → chạm hoặc tự ăn sau 3 s → ăn → vui → GET tiến độ thật → nhích thanh / lễ lớn lên → ack; SUPPORTIVE: không món ăn, không ăn mừng; GROWTH khi mở app thấy `pending_celebration_stage`).
- Nối vào `patient/page.tsx`: đường ảnh (đọc lại trạng thái liều sau xác minh) và đường tự khai. Flag tắt thì giao diện cũ giữ nguyên.
- **Smoke test trên trình duyệt thật (backend + DB test local, dữ liệu seed thử):** tự khai liều → FEED → "Cho Capy ăn" → ăn → vui → **"Capy đã lớn thành Capy con!"** (mô hình giai đoạn 2) → ack → tải lại thì **không** hiện lễ lần nữa; 3D chạy suốt cả lớp phủ. Reduced-motion: 3D tĩnh, luồng xong trong khoảng 0,4 s. Không có WebGL: fallback 2D, luồng vẫn chạy.
- Test thuần `npm run test:companion`: ảnh không khớp không bao giờ ra FEED; AWAITING ra SUPPORTIVE; HTTP 200 với status PENDING không ra FEED; chống phát lại theo liều; máy trạng thái.
- **Chưa kiểm chứng trên trình duyệt:** đường SUPPORTIVE qua ảnh thật (cần VLM), mới có test thuần.

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Chưa chạy `npm run build` hay full suite.
