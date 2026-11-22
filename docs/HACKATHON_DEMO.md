# CapyMedi — Hướng dẫn chạy demo hackathon (Docker Compose, LOCAL)

Một lệnh, dữ liệu thật: PostgreSQL + FastAPI (Tesseract OCR + VLM) + Next.js trong Docker.
**Không** dùng production, **không** có phản hồi giả lập: thiếu cấu hình VLM thì app báo
"AI đếm thuốc chưa được bật", không bịa kết quả.

## 1. Yêu cầu

Docker + Docker Compose v2 (`docker compose version`). Không cần Python/Node/Tesseract trên máy host —
Tesseract (`vie`, `eng`) được cài **trong** image backend.

## 2. Cấu hình — một file `.env` ở thư mục gốc (git ignore)

```bash
cp .env.example .env    # lần đầu, rồi điền giá trị
```

Biến chính (chỉ tên — giá trị xem `.env.example`):

| Nhóm | Biến |
|---|---|
| Application | `APP_ENV` (`demo` cho stack này), `CORS_ORIGINS`, `BACKEND_HOST_PORT`, `FRONTEND_HOST_PORT`, `POSTGRES_HOST_PORT`, `NEXT_PUBLIC_API_URL`, `FRONTEND_NODE_IMAGE` |
| PostgreSQL | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (DB khởi tạo server), `CAPYMEDI_DB_NAME` (DB ứng dụng, demo = `capytest`), `DATABASE_URL` (chỉ khi chạy trên host) |
| Authentication | `INTERNAL_AUTH_SECRET`, `JWT_SECRET` |
| Supabase | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (chỉ để gửi email xác minh khi tự đăng ký) |
| OpenAI / VLM | `OPENAI_API_KEY`, `VLM_PROVIDER=openai`, `VLM_MODEL` (vd `gpt-4.1-mini`), `VLM_BASE_URL` |
| OCR | `PHOTO_OCR_EVIDENCE_ENABLED` |
| Companion | `COMPANION_ENABLED`, `COMPANION_ALLOWLIST` |
| Demo | `ENABLE_DEMO_SEED`, `CAPYMEDI_DEMO_PASSWORD`, `CAPYMEDI_DEMO_ALLOWED_DBS` |

**Thứ tự ưu tiên:** biến shell khi chạy lệnh > `.env` (Compose dùng để thay `${...}` trong
`docker-compose.yml`) ; bên trong container backend: khối `environment:` > `env_file: .env`
(Compose tự đặt `DATABASE_URL=...@db:5432/${CAPYMEDI_DB_NAME}` cho container).
Frontend **không** nhận `.env`: chỉ `BACKEND_INTERNAL_URL` + `INTERNAL_AUTH_SECRET` (server-only);
`NEXT_PUBLIC_*` được nhúng lúc build — đổi chúng phải build lại.

## 3. Khởi động

```bash
docker compose up --build -d
docker compose ps
```

Thứ tự tự động: `db` (healthy) → `migrate` (tạo DB nếu chưa có + `alembic upgrade head`, chạy xong rồi
thoát) → `backend` (healthy) → `frontend`; song song `demo-seed` chạy **một lần**:

- chỉ khi `APP_ENV=demo` **và** `ENABLE_DEMO_SEED=true` **và** DB nằm trong `CAPYMEDI_DEMO_ALLOWED_DBS`;
- **khởi tạo nếu chưa có**: đã đủ 6 tài khoản demo thì bỏ qua — chạy lại `up` **không** reset lịch sử,
  điểm hay Capy đã dùng.

URL: Frontend http://localhost:3010 · Backend http://localhost:8001 · API docs http://localhost:8001/docs

## 4. Tài khoản demo (hư cấu)

| Email | Vai trò | Mật khẩu |
|---|---|---|
| `hackathon-demo-patient1@example.com` | Bệnh nhân — uống đúng giờ | `CAPYMEDI_DEMO_PASSWORD` |
| `hackathon-demo-patient2@example.com` | Bệnh nhân — trễ/bỏ liều | `CAPYMEDI_DEMO_PASSWORD` |
| `hackathon-demo-patient3@example.com` | Bệnh nhân — xác nhận bằng ảnh | `CAPYMEDI_DEMO_PASSWORD` |
| `hackathon-demo-doctor1@example.com` | Bác sĩ của BN1 | `CAPYMEDI_DEMO_PASSWORD` |
| `hackathon-demo-doctor2@example.com` | Bác sĩ của BN2 | `CAPYMEDI_DEMO_PASSWORD` |
| `hackathon-demo-doctor3@example.com` | Bác sĩ của BN3 | `CAPYMEDI_DEMO_PASSWORD` |

Xem mật khẩu trên máy của bạn: `grep '^CAPYMEDI_DEMO_PASSWORD=' .env | cut -d= -f2-`

## 5. Lệnh vận hành

```bash
docker compose logs -f backend                                   # log
docker compose exec backend python scripts/demo/health.py        # sức khoẻ (không gọi VLM)
docker compose exec backend python scripts/demo/health.py --probe-vlm   # gọi VLM THẬT 1 lần (tốn phí)
docker compose run --rm demo-seed --prepare-patient3             # NGAY TRƯỚC GIỜ DEMO
docker compose run --rm demo-seed --reset                        # chủ động tạo lại dữ liệu demo
docker compose down                                              # dừng (giữ dữ liệu)
```

Trạng thái health: `HEALTHY` · `UNHEALTHY` · `UNAVAILABLE` · `NOT CONFIGURED` · `UNVERIFIED`
(VLM đã cấu hình nhưng chưa gọi thử — chỉ `--probe-vlm` mới cho `HEALTHY`).

`--prepare-patient3` chỉ đưa **một** liều PENDING sắp tới của BN3 vào khung xác nhận (+5 phút);
đã có liều đang trong khung thì không làm gì. Không bao giờ chạy tự động khi `up`.

## 6. Kịch bản trình diễn

1. **BN1** — lịch sử 7 ngày 100%, điểm, Capy.
2. **BN2** — lịch sử 60%: 3 "Muộn", 2 "Bỏ liều"; điểm có thể âm theo luật trừ điểm hiện hành.
3. **BN3** — "Chụp ảnh xác nhận" → ảnh nhãn thuốc → dòng **Đọc chữ (OCR)** (Tesseract thật) và
   **AI đếm thuốc** (VLM thật nếu cấu hình). Ảnh **không chứng minh đã uống** — người bệnh tự xác nhận.
4. Điểm thưởng cập nhật; **Cho Capy ăn** → % tăng.
5. **BS1/BS3** — `/doctor/prescribe` → "Chốt phác đồ & gửi duyệt" → "Duyệt & kích hoạt".
6. **BS2** — `/doctor/patients`.
7. `docker compose down && docker compose up --build -d` — dữ liệu còn nguyên.

## 7. Dữ liệu & an toàn

- Volume `capymedi_pgdata` (PostgreSQL: `vmec04` cũ + `capytest` demo) và `capymedi_photos` (ảnh).
- **Không** dùng `docker compose down -v` — xoá volume là **mất toàn bộ dữ liệu**.
- Kiểm chứng dữ liệu đến từ PostgreSQL:
  ```bash
  docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d capytest -c "select patient_id, status, count(*) from dose_event where patient_id like '"'"'hackathon-demo%'"'"' group by 1,2 order by 1,2"'
  ```
- Seed từ chối: DB ngoài allowlist, host không phải local/`db`, `APP_ENV=production`, thiếu mật khẩu.

## 8. Sự cố thường gặp

| Hiện tượng | Xử lý |
|---|---|
| `Du lieu demo NOT CONFIGURED` | Kiểm tra `APP_ENV=demo`, `ENABLE_DEMO_SEED=true`; `docker compose logs demo-seed` |
| BN3 không có liều trong khung giờ | `docker compose run --rm demo-seed --prepare-patient3` |
| `VLM NOT CONFIGURED` | Đặt `VLM_MODEL` + `OPENAI_API_KEY` trong `.env`, `docker compose up -d backend` |
| Cổng 3010/8001/5432 bận | Đổi `*_HOST_PORT` trong `.env` (đổi cổng backend thì đổi cả `NEXT_PUBLIC_API_URL` + build lại) |
| Kéo image Node chậm | Đặt `FRONTEND_NODE_IMAGE` thành image Node ≥ 20 đã có sẵn |
