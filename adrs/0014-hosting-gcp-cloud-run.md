# ADR-0014: Chuyển hosting từ Railway sang Google Cloud (Cloud Run + Cloud SQL)

**Status:** Superseded by [ADR-0015](./0015-hosting-single-vps-docker-compose.md) (2026-11-09 — hết credit GCP)
**Ngày:** 2026-11-04
**Người đề xuất:** Nguyễn Minh Đạt (Team Leader) — soạn cùng AI agent
**Người duyệt:** `[chờ duyệt — Trương Quốc Trường (Tech Leader/Ops)]`

## Bối cảnh (Context)

Project Railway `VMEC-04` (cả 3 service `VMEC-04/FE`, `VMEC-04/BE`, `Postgres`, cùng volume ảnh) đã bị
xoá nhầm. Cả hai URL production đều trả 404 và **không còn backup database**. Toàn bộ biến môi trường
production (lưu trong service variables của Railway) cũng mất theo.

Cần dựng lại bản demo. Team chọn chuyển sang Google Cloud (project `capymedi-513714`) và chuyển code
sang repo mới `Dyo31122005/capymedi` (private, giữ nguyên lịch sử git).

ADR-0006 chỉ ghi "Docker, GitHub Actions, Railway" ở tầng DevOps, nên đổi nền tảng hosting cần ADR này.

## Quyết định (Decision)

| Thành phần | Trên Railway (cũ) | Trên GCP (mới) |
|---|---|---|
| Backend FastAPI | service `VMEC-04/BE` | Cloud Run service `capymedi-be` (region `asia-southeast1`) |
| Frontend Next.js | service `VMEC-04/FE` | Cloud Run service `capymedi-fe` (region `asia-southeast1`) |
| PostgreSQL 16 + pgvector | service `Postgres` | Cloud SQL for PostgreSQL 16 `capymedi-db` |
| Ảnh xác nhận liều + ảnh thuốc | Railway Volume | Cloud Storage bucket, mount vào Cloud Run qua Cloud Storage FUSE |
| Secret | Railway service variables | Secret Manager |
| Build image | `railway up` (build trên Railway) | Cloud Build → Artifact Registry |

Ràng buộc bắt buộc đi kèm:

1. **Backend chạy đúng 1 instance, luôn bật** (`min-instances=1`, `max-instances=1`,
   `--no-cpu-throttling`). Lý do: scheduler nhắc thuốc / escalation (APScheduler, ADR-0007) chạy
   **trong tiến trình** backend. Cloud Run scale về 0 hoặc giới hạn CPU ngoài request sẽ làm cron
   không chạy; nhiều instance sẽ chạy trùng job.
2. Không thay đổi code nghiệp vụ, contract API, hay schema DB. Migration vẫn chạy bằng
   `alembic upgrade head` lúc container khởi động như trước.
3. Database mới chỉ nạp **dữ liệu tham chiếu** (catalog thuốc V1/V2, RAG corpus đã embed, ảnh thuốc +
   embedding) copy từ DB dev local, **không** nạp tài khoản/chat/đơn thuốc dev.
4. Kết nối từ Cloud Run tới Cloud SQL qua Unix socket (`/cloudsql/<connection-name>`), không mở
   public IP cho ứng dụng. Public IP chỉ bật tạm khi nạp dữ liệu, xong thì gỡ authorized network.

## Vì sao (Rationale)

- **Cloud Run** chạy thẳng 2 Dockerfile hiện có (backend, `frontend/`), gần như không đổi gì —
  giống mô hình "1 service = 1 container" của Railway.
- **Cloud SQL** hỗ trợ sẵn `vector`, `pg_trgm`, `unaccent` (migration 0001 cần cả 3), có backup tự
  động — bài học trực tiếp từ sự cố mất DB lần này.
- **Cloud Storage FUSE** giữ nguyên cách code đọc/ghi ảnh qua đường dẫn thư mục
  (`PHOTO_STORAGE_DIR`, `DRUG_IMAGE_STORAGE_DIR`), không phải sửa code storage.

Phương án đã cân nhắc và loại bỏ:

- **1 VM Compute Engine + docker compose:** rẻ hơn, nhưng phải tự lo HTTPS, domain, backup DB và
  vá OS. Không còn ai giữ vai trò Ops toàn thời gian sau Demo Day.
- **Cloud Scheduler gọi endpoint thay cho APScheduler trong tiến trình:** cho phép backend scale
  về 0 (rẻ hơn), nhưng phải sửa code scheduler — ngoài phạm vi khôi phục khẩn cấp. Nên quay lại
  nếu sản phẩm đi tiếp.

## Vì sao thân thiện với AI + Team

- Hạ tầng mô tả bằng lệnh `gcloud` trong [`../docs/DEPLOY.md`](../docs/DEPLOY.md) và
  [`../scripts/deploy_gcp.ps1`](../scripts/deploy_gcp.ps1), chạy lại được, không phụ thuộc thao tác
  bấm tay trên dashboard.
- Không đổi code ứng dụng → mọi spec/contract/ADR khác vẫn đúng nguyên văn.

## Hệ quả (Consequences)

**Tích cực:**
- Có backup DB tự động hằng ngày (Cloud SQL), tránh lặp lại sự cố mất dữ liệu.
- Secret tập trung ở Secret Manager thay vì nằm rải rác trong biến service.

**Đánh đổi / rủi ro:**
- **Chi phí luôn chạy:** backend 1 instance không throttle CPU + Cloud SQL `db-g1-small` tốn khoảng
  vài chục USD/tháng, dùng credit GCP. Cần theo dõi billing.
- Dữ liệu người dùng production cũ (tài khoản, đơn thuốc, lịch sử chat, safety policy đã được bác
  sĩ duyệt) **mất vĩnh viễn** — phải tạo lại tài khoản demo và duyệt lại safety policy.
- Supabase Auth phải cập nhật Site URL / Redirect URLs sang domain Cloud Run mới, nếu không đăng
  nhập Google sẽ lỗi.
- CI chuyển từ runner self-hosted `cohort3` (của org) sang runner GitHub-hosted, vì repo cá nhân
  không dùng được pool runner của org. Workflow auto-deploy Railway bị gỡ, deploy GCP hiện chạy
  tay; auto-deploy qua Workload Identity Federation để làm sau.

## Câu chốt

> Dựng lại đúng như cũ trên nền mới, không đổi code nghiệp vụ — và lần này có backup.
