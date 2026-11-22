# TASK-024: Nút "Tham quan" — đăng nhập nhanh vào tài khoản khách theo vai trò

**Domain:** `auth`
**Owner:** Nguyễn Minh Đạt + AI
**Sprint:** sau Demo Day (khôi phục production trên GCP, ADR-0014)
**Status:** In Review

## Mục tiêu (Goal)

Người dùng thử (giám khảo, người được mời xem demo) bấm một nút trên trang đăng nhập, chọn
**Bác sĩ** hoặc **Bệnh nhân**, và vào thẳng tài khoản khách đã tạo sẵn — không cần biết email/mật
khẩu, không cần Google/Supabase. Mật khẩu tài khoản khách không nằm trong mã frontend, và một người
thử không thể làm hỏng nút của người khác (đổi mật khẩu).

## Acceptance Criteria (AC)

- [x] `GET /api/v1/auth/guest-login` (public) trả `{"enabled": bool, "roles": [...]}` — `roles` chỉ
      gồm vai trò có tài khoản khách đang dùng được (tồn tại, `active`, đúng role).
- [x] `POST /api/v1/auth/guest-login` (public) nhận `{"role": "doctor" | "patient"}`, trả **cùng shape**
      với `POST /auth/login` cho tài khoản khách của role đó.
- [x] Tắt mặc định: chỉ chạy khi `GUEST_LOGIN_ENABLED=true`; tắt thì `POST` trả `404`, `GET` trả
      `enabled=false`. Email tài khoản khách cấu hình qua `GUEST_DOCTOR_EMAIL` / `GUEST_PATIENT_EMAIL`.
- [x] Fail-closed: role không có tài khoản khách hợp lệ (chưa cấu hình, không tồn tại, bị khoá, sai
      role) → `404`, không bao giờ phát token cho tài khoản khác.
- [x] Tài khoản khách **không đổi được mật khẩu** (`POST /auth/change-password` → `403`).
- [x] Trang `/login` hiện khối "Tham quan" với 2 nút khi backend báo `enabled=true`, ẩn hoàn toàn khi
      tắt; bấm nút → vào `/doctor` hoặc `/patient` như đăng nhập thường, phiên giữ được sau F5.
- [x] Contract cập nhật ở `specs/api-contracts.md` §1 + §1c-5.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [x] `/specs/user-roles.md` — ma trận quyền (tài khoản khách là `doctor`/`patient` bình thường)
- [x] `/specs/api-contracts.md` §1 `auth-api`
- [x] `/adrs/0014-hosting-gcp-cloud-run.md`
- [x] `AGENTS.md`

## Subtask

- [x] Backend: settings, schema, 2 endpoint, chặn đổi mật khẩu — `backend/api/auth_routes.py`
- [x] Test API trên Postgres thật — `tests/test_api/test_auth_guest_login.py`
- [x] Frontend: route BFF `/api/auth/guest-login` (lưu refresh cookie giống `/api/auth/login`),
      `loginAsGuest()` trong `lib/auth.tsx`, khối nút trên `app/login/page.tsx`
- [x] Bật trên production GCP + smoke test

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md), thêm:

- [x] Tắt `GUEST_LOGIN_ENABLED` là gỡ hẳn tính năng, không cần deploy lại frontend.

## Ghi chú / trao đổi thêm

- **Rủi ro dữ liệu (đã báo người phụ trách 2026-11-05):** bác sĩ khách là một tài khoản `doctor`
  thật — hiện danh sách bệnh nhân của bác sĩ không lọc theo liên kết, nên bác sĩ khách **thấy mọi
  bệnh nhân trong hệ thống**. Chỉ bật `GUEST_LOGIN_ENABLED` khi hệ thống chỉ có dữ liệu demo; khi
  có người dùng thật thì tắt đi.
- Người thử vẫn sửa được dữ liệu demo (kê đơn, chat…) — chấp nhận cho môi trường demo; muốn làm
  sạch thì admin xoá/tạo lại tài khoản khách.
- Chọn backend cấp phiên thay vì nhúng mật khẩu vào frontend (người phụ trách chốt 2026-11-05): mật
  khẩu nhúng sẽ lộ trong bundle JS và một người đổi mật khẩu là nút hỏng với mọi người.
