# TASK-CAPY-01: Xác minh `DOSE_RUNTIME_MODE` ở production

**Domain:** `scheduling` (vận hành)
**Owner:** Operator có quyền Railway + AI
**Sprint:** `[chưa xếp sprint]`
**Status:** Blocked — cần người có quyền đọc Railway

## Mục tiêu (Goal)

Xác định runtime liều đang chạy ở service `VMEC-04/BE` production (`legacy` / `shadow` / `v2`). Companion chỉ hỗ trợ `legacy`/`shadow` ([ADR-0016](../adrs/0016-capybara-companion-domain.md)). Đây là release blocker **B-1**.

## Acceptance Criteria (AC)

- [ ] Ghi được giá trị `DOSE_RUNTIME_MODE` của production, hoặc ghi rõ "không đặt" (nghĩa là mặc định `legacy`, theo `backend/config.py:324`).
- [ ] Đối chiếu bằng dữ liệu: số dòng `dose_occurrence` tạo trong 7 ngày gần nhất (> 0 nghĩa là `shadow`/`v2` đang ghi V2).
- [ ] Cập nhật §2.3 của [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md).
- [ ] Không chép biến môi trường nào khác ra ngoài; không đổi cấu hình production.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`docs/DEPLOY.md`](../docs/DEPLOY.md) mục "Environment variables"
- [ ] `backend/config.py` (`dose_runtime_mode`)

## Cách làm

```bash
railway variables --service "VMEC-04/BE" --kv | grep '^DOSE_RUNTIME_MODE='   # chỉ in đúng một key
```

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Không có code.

## Ghi chú / trao đổi thêm

**2026-11-14 (AI, lần chạy đầu):** **UNKNOWN.** Máy dev không có Railway CLI lẫn `psql`. `.env` local có 26 key, **không** có key `RAILWAY_*` nào (file kéo bằng `railway variables --kv` sẽ có), nên không phải bản sao env production và không dùng làm bằng chứng được. Bằng chứng duy nhất vẫn là comment ngày 2026-08-20 trong `backend/services/dose_push_reminder.py` ("production dang shadow"), mức tin cậy yếu. Cần người có quyền Railway chạy lệnh ở trên.
