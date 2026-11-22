# Audit dữ liệu thật cho demo hackathon — 2026-11-14

Phạm vi: chạy app với FE Next.js thật + FastAPI thật + PostgreSQL thật (DB local dùng một lần
`capytest`), Tesseract OCR thật, **không** VLM giả lập. Không đụng production, không commit.

## 1. Runtime đã kiểm chứng

| Thành phần | Thực tế |
|---|---|
| Frontend | `next dev` :3010 (`NEXT_PUBLIC_API_URL=http://localhost:8001`) |
| Backend | `uvicorn backend.main:app` :8001 — **không** còn `mock_vlm_server.py` |
| DB | PostgreSQL 16 (container `capymedi-test-pg`, 127.0.0.1:55432, db `capytest`), Alembic head `0066` (1 head) |
| Dose runtime | `legacy` (mặc định) |
| OCR | Tesseract 5.3.4 vie+eng (bản giải nén local), `PHOTO_OCR_EVIDENCE_ENABLED=true` chỉ ở local |
| VLM | **UNAVAILABLE** — `.env` không có `VLM_MODEL`/`VLM_API_KEY`; app báo đúng, không giả lập |
| Companion | `COMPANION_ENABLED=true` + allowlist `hackathon-demo-patient` chỉ ở local (mặc định TẮT) |
| Job nền | 10 job APScheduler đăng ký 1 lần/job (gồm `_run_companion_reconcile`), không lỗi |

## 2. Lỗi đã sửa

| # | Mức | Vấn đề (nguyên nhân gốc) | Sửa |
|---|---|---|---|
| 1 | P0 | `GET /doses`, 4 route ảnh chỉ gác `X-Internal-Secret` — header do **proxy FE tự gắn** → ai gọi được FE cũng đọc lịch thuốc/**ảnh thuốc (PHI)** của bệnh nhân khác và **gửi ảnh thay họ** (đổi trạng thái liều + cộng điểm) | `security.kiem_tra_quyen_du_lieu_benh_nhan` (chính mình / người thân `accepted` / bác sĩ / admin) + JWT bắt buộc; proxy chuyển tiếp `Authorization`; FE gắn token (biến bộ nhớ, không storage); ảnh tải bằng fetch+JWT |
| 2 | P0 | `GET /prescriptions` trả phác đồ **mọi** bệnh nhân cho bất kỳ ai; `PUT /prescriptions/{id}` **không cần đăng nhập** | Danh sách toàn hệ thống chỉ bác sĩ/admin; theo `patient_id` cần quyền; PUT chỉ bác sĩ/admin |
| 3 | P1 | `GET /caregiver-links` lộ ai theo dõi ai | Cùng quy tắc quyền |
| 4 | P1 | Mọi đơn thuốc ghi `doctor_id = demo-doctor-01` (hằng số FE) | Backend lấy `doctor_id` từ JWT bác sĩ khi có |
| 5 | P0 (demo) | VLM chưa cấu hình → báo "Hệ thống đang bận, thử lại" (sai sự thật) | `vlm_status=UNAVAILABLE` + câu đúng; OCR chạy **trước** VLM nên bằng chứng OCR thật vẫn có; UI tách "Đọc chữ (OCR)" / "AI đếm thuốc" |
| 6 | P1 | Khớp ảnh nhưng OCR mâu thuẫn → im lặng hiển thị thành công | Toast cảnh báo (quyết định ADR-0011 giữ nguyên) |
| 7 | P1 | Lịch sử ẩn liều đã uống cho tới khi hết khung giờ | Liều đã báo cáo hiện ngay |
| 8 | P2 | Bệnh nhân tải dữ liệu toàn hệ thống của bác sĩ (phác đồ/audit/danh sách BN) khi mở app | Chỉ nhân viên y tế mới tải |
| 9 | Demo | Seed demo cũ chèn thẳng `dose_event`, tắt chụp ảnh | `scripts/seed_hackathon_demo.py`: bác sĩ đăng nhập → kê đơn → duyệt qua API thật |

Mock runtime: `mock_vlm_server.py` (scratchpad, chưa từng nằm trong repo) đã dừng. Không tìm thấy mock
runtime nào khác trong luồng bệnh nhân: `proto-store` khởi tạo rỗng và tải từ API; `admin-mock.ts`
chỉ còn hàm nhãn; mảng hằng còn lại là nội dung UI tĩnh.

## 3. Ma trận nguồn sự thật (đã chạy thật)

| Tính năng | API | Bảng DB | Kết quả |
|---|---|---|---|
| Đăng nhập | `POST /auth/login`, `/auth/me` | `account` | PASS |
| Phác đồ (kê + duyệt) | `POST /prescriptions`, `/approve` | `prescription` | PASS (qua seed API, `doctor_id` từ JWT) |
| Lịch liều | `GET /doses` | `dose_event` (14 liều sinh tự động) | PASS |
| Chụp ảnh + OCR | `POST /doses/{id}/photo` | `photo_verification.evidence` | PASS (OCR thật đọc "5 mg") |
| VLM | — | — | **UNAVAILABLE** (báo đúng, không trừ lượt) |
| Xác nhận liều | `PATCH /doses/{id}` | `dose_event`, `system_audit_logs` | PASS (`first_reported_at`, audit) |
| Xác nhận trùng | `PATCH` lần 2 | — | PASS (không thêm điểm/Capy) |
| Điểm thưởng | `GET /rewards/me` | `patient_reward_event`/`_account` | PASS (UI 5 điểm = DB) |
| Capy | `GET /companion/me` | `companion_care_day` | PASS (16%, giữ sau reload + restart backend) |
| Lịch sử | `GET /doses` | `dose_event` | PASS (sau sửa #7) |
| Người thân xem BN | `GET /caregiver-links`, `/doses` | `caregiver_link` | PASS |
| Người thân duyệt | `PATCH` (caregiver) | `dose_event` | PARTIAL — chỉ test DB; không tạo được `AWAITING_CAREGIVER` qua UI khi VLM tắt |
| Cách ly dữ liệu | proxy FE | — | PASS (401/403 đúng) |
| Bác sĩ trên trình duyệt | — | — | UNVERIFIED (đăng nhập bác sĩ dùng OTP email) |

## 4. Chạy demo

```bash
# 1. Postgres dùng một lần (đã có): docker start capymedi-test-pg
export DATABASE_URL=postgresql://capytest:capytest@127.0.0.1:55432/capytest  # DB demo local
export APP_ENV=development INTERNAL_AUTH_SECRET=... JWT_SECRET=... OPENAI_API_KEY=...
export COMPANION_ENABLED=true COMPANION_ALLOWLIST=hackathon-demo-patient
export PHOTO_OCR_EVIDENCE_ENABLED=true CORS_ORIGINS=http://localhost:3010
export PATH=$HOME/tools/tesseract/bin:$PATH     # Tesseract local
# (tuỳ chọn) VLM thật: VLM_MODEL, VLM_API_KEY, VLM_BASE_URL
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_drug_catalog.py          # 1 lần
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8001
.venv/bin/python scripts/seed_hackathon_demo.py --api http://127.0.0.1:8001   # tái chạy được
cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8001 INTERNAL_AUTH_SECRET=... npx next dev -p 3010
```

Tài khoản demo (hư cấu, mật khẩu `CapyDemo#2026`): `hackathon-patient@example.com`,
`hackathon-caregiver@example.com`, `hackathon-doctor@example.com`.

## 5. Còn lại

- **P0 demo:** VLM thật chưa có credential → phần "AI đếm thuốc" chưa demo được.
- **P1:** `verify_patient_access`/quy tắc mới cho **mọi bác sĩ** xem mọi bệnh nhân (chưa có bảng phân công).
- **P1:** Người thân duyệt liều chưa E2E trên UI; luồng bác sĩ trên trình duyệt chưa E2E (OTP).
- **P2:** Bệnh nhân vẫn gọi `/api/escalations` (401/403 trong console).
- Chính sách cần duyệt: tự chốt TAKEN sau 3 lần ảnh lệch khi không có người thân; mâu thuẫn OCR↔VLM.
- Chưa chạy `pnpm build` (dev server đang dùng `.next`); đã chạy `tsc --noEmit` + eslint file sửa.
