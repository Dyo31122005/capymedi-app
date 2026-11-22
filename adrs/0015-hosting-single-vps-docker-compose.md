# ADR-0015: Hosting trên 1 VPS (Contabo) bằng Docker Compose

**Status:** Proposed
**Ngày:** 2026-11-09
**Người đề xuất:** Nguyễn Minh Đạt (Team Leader) — soạn cùng AI agent
**Người duyệt:** `[chờ duyệt — Trương Quốc Trường (Tech Leader/Ops)]`
**Thay thế:** [ADR-0014](./0014-hosting-gcp-cloud-run.md)

## Bối cảnh (Context)

ADR-0014 dựng lại production trên Google Cloud (Cloud Run + Cloud SQL) bằng credit dùng thử. Credit
đã hết ngày 2026-11-09: billing bị tắt, Cloud SQL dừng, backend trả 503. Chi phí ước tính để chạy
tiếp trên GCP là khoảng 95 USD/tháng — quá lớn cho một bản demo sau Demo Day.

Cần một chỗ chạy **rẻ, công khai, chạy 24/7** (bộ nhắc thuốc nằm trong tiến trình backend, ADR-0007).

## Quyết định (Decision)

Chạy toàn bộ hệ thống trên **1 VPS Contabo Cloud VPS 4** (4 vCPU, 8 GB RAM, 100 GB SSD, region EU,
Ubuntu 24.04, khoảng 6,60 USD/tháng) bằng **Docker Compose** (`deploy/vps/docker-compose.yml`):

| Service | Image | Ghi chú |
|---|---|---|
| `db` | `pgvector/pgvector:pg16` | Không mở cổng ra ngoài; volume `pgdata` |
| `backend` | build từ `Dockerfile` | 1 container duy nhất (APScheduler); `mem_limit: 5g` |
| `frontend` | build từ `frontend/Dockerfile` | `NEXT_PUBLIC_API_URL=https://$DOMAIN` |
| `caddy` | `caddy:2` | Cửa vào duy nhất 80/443, tự xin HTTPS (Let's Encrypt) |

- **Một domain cho cả web và API:** Caddy chuyển `/api/v1/*`, `/health`, `/docs` sang backend, còn
  lại sang frontend. Domain mặc định `capymedi.185-176-252-232.sslip.io` (miễn phí, không cần mua).
- **Ảnh** lưu ở thư mục `/opt/capymedi/storage` trên VPS (bind mount), tồn tại qua mọi lần deploy.
- **Secret** ở `/opt/capymedi/.env` (quyền 600, không commit); mẫu ở `deploy/vps/.env.example`.
- **Backup DB:** cron hằng ngày `pg_dump` vào `/opt/capymedi/backups`, giữ 14 bản.
- **Deploy:** `scripts/deploy_vps.sh` đóng gói đúng commit `HEAD`, build trên VPS, smoke test.
- Tường lửa `ufw` chỉ mở 22, 80, 443. Đăng nhập SSH bằng key, user `ubuntu`.

Không đổi code nghiệp vụ, contract API hay schema DB.

## Vì sao (Rationale)

- Rẻ nhất trong các phương án chạy 24/7 đủ 8 GB RAM: khoảng 6,60 USD/tháng so với khoảng 43 USD/tháng
  trên Railway và khoảng 95 USD/tháng trên GCP.
- Docker Compose dùng lại nguyên 2 Dockerfile đã chạy ổn trên Railway và Cloud Run.

Phương án đã cân nhắc và loại bỏ:

- **Railway** (production trước ADR-0014): nhanh dựng nhất nhưng khoảng 43 USD/tháng cho 4 GB RAM chạy liên tục.
- **Oracle Cloud Always Free:** miễn phí nhưng hạn mức ARM đã giảm còn 2 OCPU / 12 GB, thường hết chỗ,
  phải build lại image ARM, và có rủi ro thu hồi máy.
- **Ghép các gói miễn phí** (Vercel + Supabase DB + Hugging Face Spaces): DB miễn phí 500 MB sát dung
  lượng dữ liệu thuốc kèm vector; backend miễn phí tự ngủ làm bộ nhắc thuốc không chạy.
- **Chạy trên laptop + Cloudflare Tunnel:** miễn phí nhưng máy phải bật liên tục.

## Vì sao thân thiện với AI + Team

- Toàn bộ hạ tầng nằm trong repo (`deploy/vps/`), dựng lại được trên bất kỳ VPS Ubuntu nào.
- Một lệnh deploy, có smoke test.

## Hệ quả (Consequences)

**Tích cực:**
- Chi phí giảm khoảng 14 lần so với GCP.
- Có backup DB hằng ngày trên máy.

**Đánh đổi / rủi ro:**
- **Một máy duy nhất:** VPS hỏng là cả hệ thống ngừng. Backup nằm cùng máy — nên định kỳ tải bản
  backup về máy khác.
- Team phải tự lo cập nhật bảo mật hệ điều hành (Ubuntu tự cài bản vá bảo mật qua unattended-upgrades).
- Region EU: độ trễ từ Việt Nam khoảng 200–250 ms (region Singapore hết hàng lúc mua). Không đáng kể so
  với thời gian trả lời của LLM.
- Chưa có auto-deploy từ GitHub Actions; deploy chạy tay bằng script.

## Câu chốt

> Một máy, một lệnh deploy, chi phí bằng một ly cà phê mỗi tuần.
