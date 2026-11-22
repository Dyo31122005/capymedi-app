# Deploy

> **Cập nhật 2026-11-09 — production chạy trên 1 VPS Contabo (ADR-0015).** Credit Google Cloud đã hết;
> mục **Google Cloud** và **Railway** phía dưới chỉ còn để tra lịch sử.

## VPS Contabo (hiện tại)

| | |
|---|---|
| Web + API | https://capymedi.185-176-252-232.sslip.io (Caddy: `/api/v1/*` → backend, còn lại → frontend) |
| Máy | Contabo Cloud VPS 4 (4 vCPU / 8 GB / 100 GB SSD, EU, Ubuntu 24.04) — `185.176.252.232` |
| Đăng nhập SSH | `ssh -i ~/.ssh/capymedi_vps ubuntu@185.176.252.232` (root login tắt; ufw chỉ mở 22/80/443) |
| Thư mục | `/opt/capymedi`: `.env` (secret, 600) · `current` → `releases/<sha>` · `storage/` (ảnh) · `backups/` |
| Compose | `deploy/vps/docker-compose.yml` — `db` (pgvector), `backend`, `frontend`, `caddy` |

### Deploy
```bash
./scripts/deploy_vps.sh      # Git Bash, từ root repo: đóng gói commit HEAD → build trên VPS → smoke test
```
Chỉ deploy những gì **đã commit**. Giữ 3 bản gần nhất trong `releases/`; quay lại bản cũ:
`ln -sfn /opt/capymedi/releases/<sha> /opt/capymedi/current && cd /opt/capymedi/current/deploy/vps && docker compose --env-file /opt/capymedi/.env up -d --build`.

### Xem log / thao tác
```bash
cd /opt/capymedi/current/deploy/vps
docker compose --env-file /opt/capymedi/.env ps
docker compose --env-file /opt/capymedi/.env logs --tail 100 backend
```
Đổi biến môi trường (vd tắt nút tham quan `GUEST_LOGIN_ENABLED=false`): sửa `/opt/capymedi/.env` rồi
`up -d backend`. Biến `NEXT_PUBLIC_*` là build-time → phải `up -d --build frontend`.

### Backup
`deploy/vps/backup.sh` — `pg_dump` vào `/opt/capymedi/backups`, giữ 14 bản. Lịch chạy (cron của user
`ubuntu`, giờ VPS là Europe/Berlin → 21:15 Berlin ≈ 03:15 giờ Việt Nam): `15 21 * * * /opt/capymedi/current/deploy/vps/backup.sh >> /opt/capymedi/backups/backup.log 2>&1`.
Backup nằm cùng máy với DB — định kỳ tải về máy khác (`scp`).

### Dựng lại từ đầu trên VPS mới (đã làm 2026-11-09)
1. Ubuntu 24.04, gắn SSH key; cài Docker (`get.docker.com`), `ufw allow 22,80,443`.
2. Tạo `/opt/capymedi/{storage/{photo_verifications,drug_images,drug_image_chat_doctor_private},backups,releases}`,
   `chown -R 1000:1000 storage` (uid của `appuser` trong image).
3. Viết `/opt/capymedi/.env` theo `deploy/vps/.env.example`, `chmod 600`.
4. `./scripts/deploy_vps.sh` (backend tự chạy migration).
5. Nạp dữ liệu tham chiếu: `pg_dump --data-only -Fc` 11 bảng (`drug`, `drug_chunks`, `rag_corpus`,
   `rag_embedding_reservation`, `rag_corpus_checkpoint`, `ingredient`, `drug_product`, `drug_id_map`,
   `drug_product_ingredient`, `drug_image`, `drug_image_embedding`) từ DB dev local →
   `pg_restore --data-only --single-transaction` vào service `db`. Ảnh thuốc: giải nén
   `local_drug_image_storage/drug-images` vào `storage/drug_images/`.
   **Sau khi nạp xong phải `restart backend`**: lúc khởi động backend dựng sẵn chỉ mục nhận diện
   ảnh/OCR từ DB — DB còn trống thì chỉ mục rỗng (`OCR catalog ... keys=0`, đúng phải là `keys=2939`).
6. Tạo super_admin: `docker compose ... exec backend python scripts/create_admin.py ...`; tài khoản khác
   tạo qua admin (bác sĩ **trước** bệnh nhân để `DoctorWatch` liên kết).
7. Supabase → Auth → URL Configuration: Site URL + Redirect URLs `https://<domain>/**`.

---

> **Cập nhật 2026-11-04 — production chuyển sang Google Cloud (ADR-0014).** Project Railway
> `VMEC-04` đã bị xoá (kể cả database, không có backup). Phần **Google Cloud** ngay dưới đây là
> cách deploy hiện tại. Các mục Railway phía sau giữ lại để tra lịch sử; mục env var / VAPID /
> Telegram vẫn đúng về ý nghĩa từng biến.

## Google Cloud (hiện tại)

| Thành phần | Tài nguyên GCP (project `capymedi-513714`, region `asia-southeast1`) |
|---|---|
| Backend FastAPI | Cloud Run `capymedi-be` — https://capymedi-be-621885002283.asia-southeast1.run.app |
| Frontend Next.js | Cloud Run `capymedi-fe` — https://capymedi-fe-621885002283.asia-southeast1.run.app |
| PostgreSQL 16 + pgvector | Cloud SQL `capymedi-db` (`db-g1-small`, backup hằng ngày 19:00 UTC, giữ 7 bản) |
| Ảnh (xác nhận liều, ảnh thuốc) | Bucket `gs://capymedi-513714-data`, mount vào backend tại `/app/data/gcs` |
| Secret | Secret Manager (`DATABASE_URL`, `JWT_SECRET`, `INTERNAL_AUTH_SECRET`, `OPENAI_*`) |
| Image | Artifact Registry `asia-southeast1-docker.pkg.dev/capymedi-513714/capymedi` |

### Deploy

```powershell
./scripts/deploy_gcp.ps1                 # backend + frontend
./scripts/deploy_gcp.ps1 -Target api     # chỉ backend
./scripts/deploy_gcp.ps1 -Target web -SupabaseUrl <url> -SupabaseAnonKey <anon key>
```

Script build bằng Cloud Build (không cần Docker ở máy), đẩy image lên Artifact Registry, deploy
Cloud Run rồi smoke test. Chưa có auto-deploy từ GitHub Actions (cần Workload Identity
Federation — việc làm sau).

### Ràng buộc phải giữ

- **Backend đúng 1 instance, luôn bật** (`--min-instances=1 --max-instances=1
  --no-cpu-throttling`). Scheduler nhắc thuốc/escalation/Telegram polling chạy *trong* tiến trình
  backend (APScheduler). Scale về 0 thì không nhắc; 2 instance thì chạy trùng job.
- `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_SUPABASE_*` là biến **build-time** — đổi thì phải build lại
  frontend (`deploy/gcp/cloudbuild.frontend.yaml` truyền chúng qua `--build-arg`).
- URL Cloud Run cố định theo tên service + project number, nên `CORS_ORIGINS` của backend và API URL
  của frontend được script tính sẵn, không phải sửa tay.
- Migration chạy tự động lúc container khởi động (`alembic upgrade head` trong `CMD`).
- **Backend cần 4GiB RAM.** Lúc khởi động backend tải model OpenCLIP ViT-B-32 (nhận diện ảnh
  thuốc) từ HuggingFace; ổ đĩa Cloud Run nằm trong RAM nên 2GiB bị OOM (revision `00002`).
  Khởi động mất khoảng 1 phút (warmup Drug Knowledge V2 ~17s + model ảnh ~25s).
- **Giữ cận trên phiên bản trong `requirements.txt`.** Build mới không chặn phiên bản từng kéo về
  SQLAlchemy 2.1 (đổi driver mặc định của `postgresql://` sang psycopg 3 → backend chết lúc
  migrate) và các bản major mới chưa test của openai/langfuse/Pillow.

### Tài khoản & xác minh email

- Backend **không tự gửi mail** (`backend/services/email.py` chỉ ghi link vào log). Xác minh email
  của tài khoản tự đăng ký đi qua Supabase (ADR-0013). Chưa cấu hình Supabase thì tài khoản tự
  đăng ký sẽ kẹt ở "chưa xác minh email".
- Tài khoản do admin tạo (`POST /api/v1/accounts`, trang quản lý tài khoản) được coi là đã xác
  minh và đăng nhập được ngay — dùng cách này để tạo bác sĩ/bệnh nhân demo.

### Kết nối Supabase Auth (đăng nhập Google, xác minh email, quên mật khẩu)

> **Hiện tại (2026-11-05):** project Supabase `capymedi`, ref `xmvnqhwbovcxemmesoje` (org `capymedi`,
> region `ap-southeast-1`, gói Free) — tạo mới bằng Supabase CLI vì project cũ không còn truy cập
> được. Bước 2 và 4 đã làm bằng `supabase config push`; bước 3 (Google) làm tay trên dashboard.
> OAuth redirect URI của Google: `https://xmvnqhwbovcxemmesoje.supabase.co/auth/v1/callback`.

Chỉ **frontend** dùng Supabase, và chỉ cần 2 giá trị **public**: `NEXT_PUBLIC_SUPABASE_URL`,
`NEXT_PUBLIC_SUPABASE_ANON_KEY`. Backend không đọc key Supabase nào; `SUPABASE_SERVICE_ROLE_KEY`
không được dùng ở đâu — không cần đặt. Frontend ↔ backend xác thực bằng `INTERNAL_AUTH_SECRET`
(đã có sẵn ở cả hai service).

1. **Lấy key** — Supabase Dashboard → project → *Project Settings → API*: copy **Project URL** và
   **anon / public key**.
2. **URL Configuration** — *Authentication → URL Configuration*:
   - *Site URL*: `https://capymedi-fe-621885002283.asia-southeast1.run.app`
   - *Redirect URLs*: thêm `https://capymedi-fe-621885002283.asia-southeast1.run.app/**`
     (phủ 3 đường app dùng: `/auth/google/callback`, `/auth/verify-email`, `/auth/reset-password`).
     Thiếu bước này Supabase sẽ chuyển người dùng về Site URL cũ (Railway, đã chết).
3. **Google provider** — *Authentication → Sign In / Providers → Google*: bật, điền Client ID /
   Client Secret của một OAuth client loại *Web application* (Google Cloud Console → *APIs &
   Services → Credentials*). Trong OAuth client đó, *Authorized redirect URI* phải là
   `https://<project-ref>.supabase.co/auth/v1/callback` — URI này trỏ về Supabase, không phải về app,
   nên nếu project Supabase cũ đã cấu hình Google thì **không phải sửa gì ở bước này**.
4. **Email** — *Authentication → Sign In / Providers → Email*: bật *Confirm email* (luồng đăng ký
   dựa vào link xác minh). SMTP mặc định của Supabase giới hạn số mail rất thấp, đủ cho demo; dùng
   thật thì cấu hình *Custom SMTP*.
5. **Build lại frontend** (biến build-time):
   ```powershell
   ./scripts/deploy_gcp.ps1 -Target web -SupabaseUrl https://<project-ref>.supabase.co -SupabaseAnonKey <anon key>
   ```

### VLM (đếm viên thuốc khi xác nhận liều bằng ảnh)

`VLM_PROVIDER=openai`, `VLM_MODEL=gpt-5.6-luna` (đổi từ `gpt-5.4` ngày 2026-11-14 theo yêu cầu; luna thận trọng hơn với viên trắng không có vỏ hộp — test03 bị coi là kẹo, tin cậy thấp, trong khi gpt-5.4 đếm 2 viên nén. Quay lại: sửa `VLM_MODEL` trong `/opt/capymedi/.env` rồi `up -d backend`), `VLM_API_KEY` lấy từ secret `OPENAI_API_KEY`, để trống
`VLM_BASE_URL` (gọi thẳng api.openai.com — production cũ đi qua `api.vilao.ai`). Đã test 2026-11-05:
3/3 ảnh hộp thuốc đếm đúng, 2–5 giây/ảnh, `json_mode=schema` chạy được (code tự chuyển
`max_tokens` → `max_completion_tokens` cho model này).

### Dựng hạ tầng lần đầu (đã làm 2026-11-04, ghi lại để dựng lại được)

```bash
gcloud services enable run.googleapis.com sqladmin.googleapis.com cloudbuild.googleapis.com   artifactregistry.googleapis.com secretmanager.googleapis.com storage.googleapis.com iam.googleapis.com
gcloud sql instances create capymedi-db --database-version=POSTGRES_16 --edition=ENTERPRISE   --tier=db-g1-small --region=asia-southeast1 --storage-type=SSD --storage-size=10   --storage-auto-increase --backup-start-time=19:00 --retained-backups-count=7   --database-flags=max_connections=100
gcloud sql databases create vmec04 --instance=capymedi-db
gcloud sql users create vmec --instance=capymedi-db --password=<sinh ngẫu nhiên>
gcloud artifacts repositories create capymedi --repository-format=docker --location=asia-southeast1
gcloud storage buckets create gs://capymedi-513714-data --location=asia-southeast1   --uniform-bucket-level-access --public-access-prevention
gcloud iam service-accounts create capymedi-be
gcloud iam service-accounts create capymedi-fe
# capymedi-be: roles/cloudsql.client + roles/secretmanager.secretAccessor (project),
#              roles/storage.objectAdmin (bucket). capymedi-fe: roles/secretmanager.secretAccessor.
```

`DATABASE_URL` trong Secret Manager dùng Unix socket của Cloud SQL:
`postgresql://vmec:<pw>@/vmec04?host=/cloudsql/capymedi-513714:asia-southeast1:capymedi-db`.

### Dữ liệu ban đầu

DB mới chỉ nạp **dữ liệu tham chiếu**, copy từ DB dev local (`docker compose up -d db`) bằng
`pg_dump --data-only` cho 11 bảng: `drug`, `drug_chunks`, `rag_corpus`,
`rag_embedding_reservation`, `rag_corpus_checkpoint`, `ingredient`, `drug_product`, `drug_id_map`,
`drug_product_ingredient`, `drug_image`, `drug_image_embedding`. Không bảng nào trong số này có
khoá ngoại sang dữ liệu bệnh nhân. Ảnh thuốc copy từ `local_drug_image_storage/drug-images` lên
`gs://capymedi-513714-data/drug_images/drug-images/` (giữ nguyên `storage_key`).

Để nạp tay: tạm thêm IP máy mình vào authorized networks của Cloud SQL
(`gcloud sql instances patch capymedi-db --authorized-networks=<ip>/32`), làm xong **gỡ ngay**
(`--clear-authorized-networks`).

Tài khoản: tạo super_admin đầu tiên bằng `scripts/create_admin.py --role super_admin`, các tài khoản
khác tạo qua giao diện admin. Supabase Auth cần thêm URL frontend mới vào **Site URL / Redirect
URLs** trong dashboard Supabase, nếu không đăng nhập Google sẽ lỗi.

---

## Railway (cũ — project đã bị xoá, chỉ để tra lịch sử)

Repo này có **2 app độc lập**, deploy vào **cùng 1 project Railway** (`VMEC-04`,
environment `production`) nhưng là **2 service riêng**:

| App | Thư mục | Service Railway | Framework | URL |
|---|---|---|---|---|
| Backend | `.` (dùng `backend/`) | `VMEC-04/BE` | FastAPI | https://vmec-04be-production.up.railway.app |
| Frontend | `frontend/` | `VMEC-04/FE` | Next.js 16 | https://vmec-04fe-production.up.railway.app |

Cùng project còn service `VMEC-04/DB` (Postgres + pgvector) mà backend dùng.

Hai app nối với nhau qua 2 biến môi trường:

```
frontend  --NEXT_PUBLIC_API_URL-->  backend
backend   --CORS_ORIGINS--------->  frontend
```

Đổi domain một bên thì **phải cập nhật biến ở bên kia**. Lưu ý bất đối xứng quan trọng:

- `CORS_ORIGINS` là **runtime var** — backend đọc lúc khởi động, nên đổi biến là Railway
  restart container và có hiệu lực ngay, **không cần build lại**.
- `NEXT_PUBLIC_API_URL` là **build-time var** — Next.js nhúng thẳng giá trị vào bundle JS
  lúc `next build`. Đổi biến này thì **phải `railway up` lại**; restart suông vẫn giữ URL
  cũ vì nó đã nằm trong file `.js` của image.

---

## Deploy thủ công

Cần `make`. Trên Windows cài một lần bằng scoop (shim tự vào PATH):

```powershell
scoop install make
```

Rồi chạy từ root repo:

```bash
make deploy         # cả hai -> production, kèm smoke test
make deploy-api     # backend  -> production
make deploy-web     # frontend -> production

make smoke          # chỉ smoke test domain production, không deploy
```

Nếu không muốn cài `make`, [scripts/deploy.ps1](../scripts/deploy.ps1) làm việc tương đương:

```powershell
./scripts/deploy.ps1                 # cả api + web -> production, kèm smoke test
./scripts/deploy.ps1 -Target api     # chỉ backend
./scripts/deploy.ps1 -Target web     # chỉ frontend
```

Hoặc gọi thẳng CLI:

```bash
railway up -c                        # backend (chạy ở root repo)
cd frontend && railway up -c         # frontend, hoặc: pnpm deploy
```

`railway up` **upload thẳng thư mục hiện tại** rồi build trên Railway (không đi qua git),
nên deploy được cả khi đang có thay đổi chưa commit. Cờ `-c` chỉ stream build log rồi
thoát — thiếu nó thì CLI bám vào log runtime và treo terminal.

## Deploy tự động (GitHub Actions)

[.github/workflows/deploy.yml](../.github/workflows/deploy.yml) chạy khi push lên `main`.
Workflow lọc theo đường dẫn: commit chỉ đụng `frontend/` sẽ **không** redeploy backend.
Chạy tay được qua tab Actions → Deploy → Run workflow (chọn `api` / `web` / `both`).

### Secrets cần thêm vào GitHub

Settings → Secrets and variables → Actions:

| Secret | Giá trị |
|---|---|
| `RAILWAY_TOKEN` | Tạo ở https://railway.com/account/tokens (project token của `VMEC-04` là đủ) |

Chỉ cần **1 secret** — service và environment truyền qua cờ `--service` / `--environment`
nên runner không cần `railway link`.

---

## Environment variables

Env lưu trên Railway, **không** đọc từ `.env` khi deploy. Xem bằng `railway variables`.

### `VMEC-04/BE` (backend)

| Biến | Ghi chú |
|---|---|
| `OPENAI_API_KEY` | |
| `INTERNAL_AUTH_SECRET` | Bắt buộc — app **từ chối khởi động** nếu còn giá trị sentinel trong source |
| `DATABASE_URL` | Reference var trỏ sang service `VMEC-04/DB` |
| `CORS_ORIGINS` | Chỉ còn `https://vmec-04fe-production.up.railway.app`. Phân tách bằng dấu phẩy, **so khớp chính xác** |
| `APP_ENV` / `APP_HOST` / `LOG_LEVEL` / `EMBEDDING_MODEL` | Cấu hình app |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_SUBJECT` | Web Push (nhắc uống thuốc khi app đã đóng). **Không bắt buộc** — xem mục dưới |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_USERNAME` | Nhắc uống thuốc qua Telegram (bù chỗ Web Push yếu trên iOS). **Không bắt buộc** — xem mục dưới |

#### Web Push (VAPID)

Nhắc giờ uống thuốc có 2 kênh: banner trong app (chạy ở client, cần tab mở) và
**Web Push** (backend chủ động đẩy, tới được cả khi bệnh nhân đã đóng hẳn app).
Kênh thứ 2 cần cặp khoá VAPID.

Bỏ trống 3 biến này thì **push tự tắt, app vẫn chạy bình thường** — cố ý không
fail-closed như `INTERNAL_AUTH_SECRET`/`JWT_SECRET`, vì thiếu VAPID chỉ là mất
một tính năng phụ chứ không phải lỗ hổng bảo mật (xem `backend/services/push.py`).

Sinh cặp khoá (1 lần, không cần đăng ký dịch vụ bên thứ 3 — VAPID là chuẩn mở):

```bash
.venv/Scripts/python -c "from py_vapid import Vapid01; from cryptography.hazmat.primitives import serialization as sz; import base64; v=Vapid01(); v.generate_keys(); b=lambda r: base64.urlsafe_b64encode(r).rstrip(b'=').decode(); print('VAPID_PRIVATE_KEY='+b(v.private_key.private_numbers().private_value.to_bytes(32,'big'))); print('VAPID_PUBLIC_KEY='+b(v.public_key.public_bytes(sz.Encoding.X962, sz.PublicFormat.UncompressedPoint)))"
```

**Mỗi môi trường 1 cặp khoá riêng** (local và production không dùng chung). Đổi
khoá thì mọi `push_subscription` cũ thành vô hiệu — bệnh nhân phải bật lại thông
báo; backend tự dọn dòng chết khi dịch vụ đẩy trả 404/410.

`VAPID_PUBLIC_KEY` phát ra cho frontend qua `GET /api/v1/push/vapid-public-key`,
**không** phải biến `NEXT_PUBLIC_*` — nên đổi khoá không cần build lại frontend.

**iOS**: bệnh nhân phải "Thêm vào Màn hình chính" (cài như PWA) và dùng iOS
≥ 16.4 thì Safari mới nhận push; tab Safari thường không nhận. Android/desktop
không cần bước này.

#### Telegram bot (nhắc uống thuốc — kênh thứ 3)

Kênh này bù đúng chỗ Web Push yếu nhất: **iOS**. Safari chỉ nhận push nếu bệnh
nhân đã "Thêm vào Màn hình chính" — việc phần lớn người cao tuổi không bao giờ
làm. Telegram thì chỉ cần có sẵn app.

Bỏ trống `TELEGRAM_BOT_TOKEN` thì **kênh tự tắt, app vẫn chạy bình thường** —
cùng nguyên tắc fail-mềm với VAPID ở trên (xem `backend/services/telegram.py`).
Frontend cũng tự ẩn hẳn mục Telegram trong Cài đặt khi server chưa cấu hình.

##### Giới hạn gốc phải biết trước khi thiết kế thêm

Bot API **không gửi được tin theo số điện thoại hay email**. `sendMessage` chỉ
nhận `chat_id`, và `chat_id` chỉ tồn tại sau khi chính bệnh nhân bấm `/start`
với bot. Đây là cơ chế chống spam cố ý của Telegram, không phải thiếu sót API.

Vì vậy mỗi bệnh nhân **bắt buộc phải ghép tài khoản một lần**. Không có cách nào
làm thay họ. Nếu cần gửi thẳng theo số điện thoại (không bắt người dùng thao tác)
thì phải dùng kênh khác — Zalo ZNS hoặc SMS.

##### Bước 1 — Tạo bot với @BotFather

Miễn phí, khoảng 2 phút, **không cần đăng ký doanh nghiệp**.

1. Mở Telegram, tìm **@BotFather** (có tick xanh)
2. Gửi `/newbot`
3. Nhập **tên hiển thị** — cái bệnh nhân nhìn thấy, ví dụ `CapyMedi`
4. Nhập **username** — phải là duy nhất toàn Telegram và **kết thúc bằng `bot`**,
   ví dụ `CapyMediReminderBot`
5. BotFather trả về token dạng `123456789:AAF-xxxxxxxxxxxxxxxxxxxxxxxxx`

Vài lệnh nên chạy thêm để bệnh nhân thấy bot đàng hoàng:

```
/setdescription   → Mình là CapyMedi, mình sẽ nhắc bạn uống thuốc đúng giờ nhé!
/setabouttext     → Trợ lý nhắc uống thuốc CapyMedi
/setuserpic       → (gửi ảnh avatar)
```

> **Token là mật khẩu của bot.** Ai có nó đều nhắn được cho toàn bộ bệnh nhân đã
> ghép. Không commit vào git, không dán vào chat nhóm. Lỡ lộ thì `/revoke` trong
> BotFather để lấy token mới.

##### Bước 2 — Điền vào `.env`

```bash
TELEGRAM_BOT_TOKEN=123456789:AAF-xxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_BOT_USERNAME=CapyMediReminderBot     # KHÔNG có @
TELEGRAM_DISPLAY_UTC_OFFSET_HOURS=7           # giờ VN
```

`TELEGRAM_BOT_USERNAME` dùng để dựng link `t.me/<username>?start=<token>`. Điền
sai thì nút "Kết nối" mở ra một bot không tồn tại.

`TELEGRAM_DISPLAY_UTC_OFFSET_HOURS` cần vì Telegram gửi **text thô** — khác Web
Push (trình duyệt tự đổi theo giờ máy). Để mặc định 0 thì bệnh nhân đọc
"hẹn 14:00" cho liều 21:00 của chính mình.

Rồi rebuild backend:

```bash
docker compose up -d --build backend
```

##### Bước 3 — Bệnh nhân ghép tài khoản

Trên web: **Cài đặt → Thông báo → Telegram → Kết nối**. Nút mở thẳng
`t.me/<bot>?start=<token>`, bệnh nhân bấm **Start**, xong.

Luồng đầy đủ phía trong:

```
Web: bấm Kết nối
  → POST /api/v1/telegram/link-token   (token dùng 1 lần, hạn 10 phút)
  → mở t.me/<bot>?start=<token>
  → bệnh nhân bấm Start
  → Telegram nhận "/start <token>"
  → job telegram_updates (60s/lần) kéo về, đổi token lấy chat_id
  → ghi bảng telegram_link → bot trả lời "Kết nối thành công!"
```

Vì bước cuối chạy theo job định kỳ nên có thể **chậm tới 60 giây** — bình thường,
không phải lỗi. Màn hình Cài đặt tự tải lại trạng thái khi bệnh nhân quay về tab.

##### Bước 4 — Kiểm tra

```bash
# Token đúng chưa (trả về thông tin bot)
curl -s "https://api.telegram.org/bot<TOKEN>/getMe"

# Đã ghép được ai chưa
docker compose exec db psql -U vmec -d vmec04 -c "SELECT patient_id, chat_id, username, enabled FROM telegram_link;"

# Job có chạy không
docker compose logs backend | grep -i telegram
```

##### Production (Railway)

```bash
railway variables --service "VMEC-04/BE" --set "TELEGRAM_BOT_TOKEN=..."
railway variables --service "VMEC-04/BE" --set "TELEGRAM_BOT_USERNAME=..."
```

**Dùng bot RIÊNG cho local và production.** Hai môi trường chung một token sẽ
tranh nhau `getUpdates` — `/start` của bệnh nhân có thể rơi vào máy dev và
production không bao giờ nhận được. Tạo thêm bot thứ hai tên `CapyMediDevBot`
cho local là xong.

##### Những chỗ dễ vấp

| Hiện tượng | Nguyên nhân |
|---|---|
| Không thấy mục Telegram trong Cài đặt | `TELEGRAM_BOT_TOKEN` rỗng, hoặc chưa rebuild backend |
| Bấm Kết nối, Telegram mở nhưng báo bot không tồn tại | `TELEGRAM_BOT_USERNAME` sai (thừa `@`, hoặc gõ nhầm) |
| Bấm Start rồi mà web vẫn hiện "Kết nối" | Chờ đủ 60s rồi quay lại tab; nếu vẫn không được, xem log job |
| Bot im lặng, log có `getUpdates that bai (HTTP 409)` | Đã đặt webhook cho bot này. Gỡ: `curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"` |
| Bot trả lời "link đã hết hạn" | Token quá 10 phút hoặc đã dùng rồi — bấm Kết nối lại lấy link mới |
| Đã ghép nhưng không nhận tin nhắc | Kiểm tra `enabled` trong `telegram_link`, và `dose_reminder_enabled` trong `patient_notification_pref` |

##### Ghi chú kỹ thuật

Bản hiện tại dùng **long-polling** (`getUpdates`, job `telegram_updates` trong
`backend/services/escalation_scheduler.py`) chứ không phải webhook — nhờ vậy chạy
được ngay trên máy local không cần domain public.

Nếu sau này chuyển sang webhook thì **phải bỏ job đó đi**: Telegram từ chối
`getUpdates` bằng lỗi 409 khi đã đặt webhook, hai cơ chế loại trừ nhau.

Hai origin `*.vercel.app` (backend cũ project `capymedi` và frontend cũ `capymedi-web`) đã được
**xoá hẳn** khỏi `CORS_ORIGINS` ngày 2026-08-13 — dự án không còn deploy trên Vercel. Frontend
production giờ là `https://vmec-04fe-production.up.railway.app` (service `VMEC-04/FE`) và đó là
origin duy nhất được phép. Biến đặt kèm `--skip-deploys` nên chỉ có hiệu lực sau lần
restart/redeploy BE kế tiếp (`settings.cors_origins` đọc một lần lúc khởi động,
`backend/main.py:58`).

### `VMEC-04/FE` (frontend)

| Biến | Giá trị | Ghi chú |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://vmec-04be-production.up.railway.app` | **Build-time** — xem ghi chú ở đầu file |
| `NEXT_TELEMETRY_DISABLED` | `1` | |

Sửa env:

```bash
railway variables                                  # liệt kê service đang link
railway variables --set "TÊN=giá trị"              # thêm/sửa (tự trigger redeploy)
railway variables --service "VMEC-04/FE"           # xem service khác
```

---

## Setup cho dev mới

Mỗi thư mục link tới **1 service riêng** — link ở root **không** tự áp cho `frontend/`:

```bash
railway login

# backend
railway link --project VMEC-04 --environment production --service "VMEC-04/BE"

# frontend
cd frontend
railway link --project VMEC-04 --environment production --service "VMEC-04/FE"
```

Kéo env về máy để chạy local:

```bash
railway variables --kv > .env             # ở root, cho backend
cd frontend && cp .env.example .env.local # frontend chỉ cần NEXT_PUBLIC_API_URL
```

---

## Những chỗ dễ vấp

**`railway up` ở `frontend/` mà chưa `railway link` thư mục đó** thì CLI đi ngược lên tìm
link của thư mục cha, rồi upload **cả repo** và build `Dockerfile` của backend vào service
frontend. Triệu chứng: build log của service FE chạy `pip install -r requirements.txt`.
Fix: `railway link` riêng trong `frontend/` (xem mục trên).

**Target port của domain phải khớp port app thật sự listen.** Railway inject `PORT=8080`,
Next.js standalone `server.js` đọc `PORT` nên listen 8080 — dù Dockerfile có `EXPOSE 3000`.
Domain trỏ sai port trả `502 Application failed to respond` mặc dù container log `✓ Ready`.
Kiểm tra ở dashboard → service → Settings → Networking.

**`HOSTNAME=0.0.0.0` là bắt buộc cho frontend.** `server.js` của Next.js standalone mặc
định bind `localhost`, Railway không route được traffic từ ngoài vào → healthcheck fail.
Đã set trong [frontend/Dockerfile](../frontend/Dockerfile).

**Đổi `NEXT_PUBLIC_API_URL` mà không build lại** thì frontend vẫn gọi URL cũ. Với Dockerfile
build, biến chỉ vào được build qua `ARG` (Docker cách ly build khỏi env của host) — và `ARG`
phải khai báo **trong đúng stage** dùng nó, không xuyên stage.

**Frontend có 2 lockfile** (`package-lock.json` + `pnpm-lock.yaml`). Dockerfile chỉ copy
`pnpm-lock.yaml` để build luôn dùng pnpm thay vì tuỳ builder đoán. Thêm dependency thì nhớ
cập nhật lockfile bằng `pnpm`, không phải `npm`.

**Backend từ chối khởi động nếu thiếu `INTERNAL_AUTH_SECRET` thật.** Sentinel
`unset-temp-auth-gate-CHANGE-ME-for-any-shared-env` nằm sẵn trong source nên bị chặn.
Triệu chứng: deploy FAILED, log có `ValidationError ... internal_auth_secret`.

**`preDeployCommand` chạy `alembic upgrade head`** ([railway.json](../railway.json)) trước
mỗi lần deploy backend. Volume **không** được mount lúc build và lúc pre-deploy, chỉ lúc
container chạy.

**Volume mount đè mất quyền của `appuser` — đã xử lý bằng entrypoint (2026-08-22).**
Railway mount Volume vào `/app/data/photo_verifications` **lúc container khởi động**,
sau khi image đã build xong. Volume đó thuộc `root`, phủ đè lên đúng thư mục mà
`RUN chown -R appuser:appuser /app` trong Dockerfile đã set quyền lúc build → `appuser`
mất quyền ghi, mọi lần bệnh nhân gửi ảnh đều `500` với
`PermissionError: [Errno 13] Permission denied`. Bug chỉ lộ trên Railway, **không**
lộ khi chạy `uvicorn` trực tiếp trên máy dev (không có container/volume nào).

Cách xử lý: [`docker-entrypoint.sh`](../docker-entrypoint.sh) chạy bằng `root` đúng lúc
volume đã mount nhưng app chưa khởi động — `chown` lại thư mục ảnh rồi `gosu appuser`
để hạ quyền trước khi chạy `CMD`. App vẫn chạy non-root như thiết kế ban đầu; chỉ có
vài chục ms đầu tiên chạy bằng root. Vì vậy Dockerfile **không** còn dòng `USER appuser`
— đừng thêm lại, nó sẽ chặn bước `chown` này và làm bug tái phát.

**Volume cho ảnh xác nhận liều (`photo_storage_dir`, mặc định `./data/photo_verifications`).**
Service `VMEC-04/BE` hiện KHÔNG có Volume nào gắn — mỗi lần redeploy, đĩa container cũ bị huỷ
và toàn bộ ảnh đã lưu biến mất (dòng DB `PhotoVerification.image_path` vẫn còn, chỉ file thật
mất — endpoint `GET /photo-verifications/{id}/image` trả `410 Gone` khi rơi vào ca này). Cách
gắn Volume:

1. Railway dashboard → service `VMEC-04/BE` → tab **Volumes** → **New Volume**.
2. Mount path đặt là **`/app/data/photo_verifications`** — **KHÔNG** mount cả `/app/data`
   (xem cảnh báo ngay dưới đây, đã có 1 lần deploy fail vì việc này).
3. Deploy sẽ tự restart service để gắn Volume — bình thường, không phải lỗi.
4. Xác nhận đã ăn: gửi 1 ảnh qua app → redeploy backend → gọi lại
   `GET /photo-verifications/{id}/image` — trước đây ra `410 Gone`, sau khi gắn Volume phải ra `200`.

**CẢNH BÁO: đừng mount Volume vào `/app/data`.** `Dockerfile` COPY sẵn dữ liệu
`data-knowledge-v2` (Data V2 rebuild) vào `/app/data/drug-knowledge-v2/` NGAY LÚC BUILD image
(`Dockerfile:38-39`, biến `DRUG_KNOWLEDGE_V2_DIR=/app/data/drug-knowledge-v2` ở dòng 28). Volume
mount ở RUNTIME sẽ đè/che mất toàn bộ thư mục đó nếu mount path là `/app/data` (Volume trống
"phủ" lên dữ liệu đã build sẵn) — `warm_v2_agent_knowledge_service()` lúc khởi động
(`backend/main.py:41`) không đọc được dữ liệu, app treo, `/health` không bao giờ trả lời được,
Railway báo "1/1 replicas never became healthy" sau 5 phút rồi đánh dấu deploy **Failed**. Đã
xảy ra thật (2026-08-17) khi làm theo đúng bước cũ (mount `/app/data`) — sửa bằng cách đổi mount
path về đúng `/app/data/photo_verifications`, chỉ trùm đúng thư mục ảnh, không đụng tới
`drug-knowledge-v2/`.

---

## Smoke test

```bash
curl https://vmec-04be-production.up.railway.app/api/v1/status
# {"status":"ready","agent":"LangGraph Agent v1.0"}

curl -X POST https://vmec-04be-production.up.railway.app/api/v1/chat \
  -H "Content-Type: application/json" -d '{"message":"xin chao"}'

# CORS — phải thấy Access-Control-Allow-Origin
curl -i -X OPTIONS https://vmec-04be-production.up.railway.app/api/v1/status \
  -H "Origin: https://vmec-04fe-production.up.railway.app" \
  -H "Access-Control-Request-Method: GET"

curl -o /dev/null -w "%{http_code}\n" https://vmec-04fe-production.up.railway.app/
# 200
```

Lưu ý: `https://vmec-04be-production.up.railway.app/` trả `404` là **đúng** — backend không
có route `/`. Health check ở `/health`, API ở `/api/v1/*`.

Xem log và trạng thái:

```bash
railway logs                    # log runtime của service đang link
railway logs --build            # log build
railway status                  # trạng thái toàn project
```
