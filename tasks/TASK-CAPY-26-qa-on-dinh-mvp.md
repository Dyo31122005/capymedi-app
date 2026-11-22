# TASK-CAPY-26: QA tập trung và ổn định MVP Capybara Companion

**Domain:** `companion`, `scheduling`, `frontend`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review — đợt 2 đã gỡ các blocker kỹ thuật; còn blocker cần **người có thẩm quyền** (xem "Đợt 2")

Kế hoạch: [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md); [`ADR-0016`](../adrs/0016-capybara-companion-domain.md).

## Môi trường QA (2026-11-14)

- Postgres 16 trong container riêng `capymedi-test-pg` (DB test, dữ liệu giả); backend `uvicorn` ở `127.0.0.1:8001` (flag bật **chỉ qua biến môi trường local**, allowlist `capy-demo-patient`); Next dev ở `:3010`.
- Trình duyệt: Google Chrome headless (WebGL qua SwiftShader), điều khiển bằng `playwright-core` (cài ngoài repo).
- Dữ liệu demo do script seed ngoài repo tạo (bệnh nhân giả, thuốc giả).

## Kết quả

| QA | Trạng thái | Bằng chứng |
|---|---|---|
| QA-01 Tự khai | PASS | Trình duyệt: "Tôi đã uống" → FEED (3D) → ăn → vui. DB: liều TAKEN, `first_reported_at` có giá trị, `companion_care_day` hôm nay = 100. Thẻ hiển thị khớp API (`0% đến Capy nhỡ`). |
| QA-02 Ảnh khớp | PARTIALLY VERIFIED | Chỉ test với VLM giả lập: `test_verifier.py::test_khop_anh_lam_capy_lon` và các test verifier hiện có. Logic FEED theo `matched === true` có test thuần. **Chưa chạy VLM thật** (không dùng khoá API thật). |
| QA-03 Ảnh sai | PASS (có ghi chú chính sách) | `matched=false` thì không bao giờ ra FEED (test thuần); AWAITING không lớn (`test_awaiting_caregiver_khong_lam_capy_lon`). Xem ghi chú bên dưới về nhánh "3 lần sai, không có người thân". Luồng chụp lại / độ tin cậy thấp giữ nguyên (không có màn Capy). |
| QA-04 Người thân | PASS (API/service) | `test_awaiting_chi_lon_khi_nguoi_than_duyet`, `test_awaiting_chi_tinh_khi_duyet_taken` (từ chối thì không lớn), `test_nguoi_than_duyet_ngay_d_cong_5_hook_loi_job_van_phuc_hoi`. **Chưa test giao diện người thân trên trình duyệt.** |
| QA-05 Gửi trùng | PASS | Trình duyệt và API: gửi lại PATCH TAKEN → 200, `points_awarded=0`, companion không đổi. DB: đúng 1 dòng DOSE_ON_TIME, 1 dòng trừ điểm, 1 dòng audit. Chống phát lại phía client: test thuần `fedSlotIds`. |
| QA-06 Lớn lên | PASS | API stage 1 → 2, `pending_celebration_stage=2`; tải đúng `capy-stage-1.glb` và `capy-stage-2.glb`; "Capy đã lớn thành Capy con!"; ack → `pending=null`, `companion.celebrated_stage=2`. |
| QA-07 Flag tắt | PASS | `GET /companion/me` trả `enabled=false, FEATURE_OFF`; `PATCH` trả 409; trang không có phần tử Capy và giữ khối quote cũ; xác nhận liều vẫn chạy (toast); DB: không có ghi companion nào. Đã bật lại flag local sau test. |
| QA-08 Fallback / a11y | PASS | Chặn GLB thì thẻ dùng ảnh 2D; "Bỏ qua" đóng lớp phủ, backend vẫn ghi tiến độ. Không WebGL thì 2D và luồng vẫn chạy; reduced-motion thì 3D tĩnh (đã kiểm ở TASK-CAPY-23). Canvas `pointer-events:none`; nút chạm Capy là `<button>` có nhãn. |
| QA-09 Tải lại | PASS | Sau ack, tải lại thì không hiện lễ lần nữa, render 3D, tiến độ lấy lại từ backend. |

## Lỗi tìm thấy và đã sửa

- **Thẻ Capy giữ số cũ** khi đóng `CareMoment` trước khi có kết quả (bấm "Bỏ qua"), hoặc khi xác nhận mà không mở màn Capy (NEUTRAL, đã cho ăn trên máy này). Sửa: `taiLaiCapy()` trong `frontend/src/app/patient/page.tsx` lấy lại `GET /companion/me`. Kiểm chứng: sau "Bỏ qua", thẻ hiện ngay "Capy con · 0%".
- **`frontend/package-lock.json` lệch** sau khi thêm `three`, `@react-three/fiber`, `@types/three` (ở HEAD file này vẫn khớp, nghĩa là team giữ đồng bộ cả hai). Sửa: `npm install --package-lock-only`. Build vẫn dùng `pnpm-lock.yaml` theo `frontend/Dockerfile`.

## Ghi chú chính sách QA-03 (cần PO quyết)

Nhánh "ảnh sai 3 lần, **không có người thân**": verifier chốt `TAKEN` (giữ 70% LP, theo chính sách hiện có), nên Capy **vẫn lớn** như với tự khai (D-17 PROPOSED), nhưng **không có màn ăn mừng** (SUPPORTIVE).

`dose_event` **không lưu nguồn xác nhận** (ảnh / tự khai / fallback), trái với tinh thần BR-4.1. Đây là khoảng trống contract, chưa sửa vì sẽ đổi schema lâm sàng. Nếu PO muốn nhánh này không làm Capy lớn, cần thêm cột nguồn xác nhận (task riêng). Cân nhắc: chặn tăng trưởng ở nhánh này sẽ khiến người đã cố chụp ảnh 3 lần nhận ít hơn người tự khai mà không chụp, tức là tạo động cơ bỏ qua bước chụp ảnh.

## Test đã chạy

- `pytest` tập trung (9 file companion và dose safety) trên Postgres: **118 passed, 0 skip, 0 fail**.
- `npm run test:companion`: OK.
- `pnpm build` (một lần): **thành công**. Chunk three.js khoảng 939 KB (chưa nén), tách riêng và tải động.
- `eslint` trên `page.tsx` sau khi sửa: sạch.

## Blocker cho pilot

1. B-1: chưa biết `DOSE_RUNTIME_MODE` ở production.
2. Các thay đổi P0 đang bật ngay (whitelist status, chặn tự duyệt AWAITING, mức trừ tự khai) **chờ Tech Lead review**; BR-8.2 và BR-8.7a (đang tắt) chờ PM, bác sĩ và Tech Lead duyệt.
3. CI `lint-and-test` không có Postgres nên **skip** toàn bộ test companion và dose safety; chưa có lần chạy ở staging.
4. Chưa chạy migration `0064`/`0065` trên staging; chưa kiểm VLM thật (QA-02); chưa test UI người thân (QA-04).
5. Quyết định PO về nhánh fallback QA-03 (trên).

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). **Chưa đạt** cho tới khi gỡ các blocker trên.


---

## Đợt 2 — Pilot readiness (2026-11-14)

### QA-03 đã sửa (theo chỉ đạo PO)

- **Bằng chứng gốc:** `backend/services/photo_verification/verifier.py` (nhánh không có người thân) **tự gán `TAKEN`** mà không có xác nhận nào của bệnh nhân.
- **Không thêm cột DB.** Nguồn xác nhận được suy ra từ dữ kiện có sẵn: `photo_verification.ket_qua` cộng `system_audit_logs` (`backend/services/scheduling/slot_summary.py::lieu_chi_fallback_anh`). "Chỉ fallback" nghĩa là: có ảnh, không ảnh nào `khop`, và không có audit `DOSE_STATUS_CHANGE … to=TAKEN|DELAYED` hay `DOSE_EXPLICIT_CONFIRM`.
- `progression.growth_done` loại các liều "chỉ fallback". Hồ sơ lâm sàng (vẫn TAKEN) và LP/SP (70%) **không đổi**.
- **Xác nhận rõ ràng sau fallback:** `PATCH /doses/{id}` `TAKEN` của chính bệnh nhân trên liều "chỉ fallback" ghi audit `DOSE_EXPLICIT_CONFIRM` và chạy hook companion; không đổi status, không đổi LP/SP. Frontend có nút "Tôi đã uống thuốc này" trên màn SUPPORTIVE (chỉ khi không có người thân); bấm xong thì ra màn cho ăn.
- Test (Postgres): ảnh khớp được tính; fallback không lớn (cả qua **verifier thật** với VLM giả: `test_fallback_khong_nguoi_than_khong_lam_capy_lon`); fallback rồi tự xác nhận thì được tính, điểm không đổi, gửi trùng không ghi thêm; người thân không thể xác nhận thay liều fallback. Các ca chờ duyệt / duyệt / tự khai / gửi trùng: test sẵn có vẫn xanh.
- **Chưa kiểm trên trình duyệt** nút "Tôi đã uống thuốc này" (màn SUPPORTIVE chỉ xuất hiện sau xác minh ảnh thật).

### Review P0 cho Tech Lead (AI soạn, **chưa phải** phê duyệt)

| Thay đổi đang bật (không có flag) | Bằng chứng tương thích | Cần ký duyệt |
|---|---|---|
| `PATCH /doses` chỉ nhận `TAKEN`/`MISSED` | Mọi nơi gọi trong FE chỉ gửi hai giá trị này (`patient/page.tsx`, `family/[id]/page.tsx`, `proto-store.tsx`); backend không có nơi gọi nội bộ nào khác | Có |
| Bệnh nhân không tự duyệt `AWAITING_CAREGIVER` | FE chỉ cho người thân duyệt (trang `family/[id]`); đã test bằng UI người thân | Có |
| Gửi trùng là no-op (không hạ TAKEN thành DELAYED, không cộng điểm, không audit) | Test V-5 và QA-05 (DB: 1 dòng cộng điểm, 1 dòng audit) | Có |
| MISSED→TAKEN do bệnh nhân tự khai bị trừ như tự khai (trước đây giữ 100%); bấm "Bỏ qua" không còn bị trừ −10 SP | Test V-3 | **Có** (đụng kinh tế điểm, nhưng là sửa bug theo đúng ý `PCT_SELF_REPORT_NO_PHOTO`) |
| Nhánh V2 không còn nhận `DELAYED`/`SKIPPED` qua PATCH | FE không gửi hai giá trị này; V2 chưa chắc đang chạy (B-1) | Có |
| **Mới:** ngoại lệ `DOSE_EXPLICIT_CONFIRM` (QA-03) | Test ở trên | Có |

### CI Postgres (đã cấu hình, **chưa chạy trên CI thật**)

- `.github/workflows/ci.yml`: thêm job `companion-db-tests` theo mẫu `golden-smoke` (pgvector:pg16, host port 5433, `alembic upgrade head`), chạy 9 file test an toàn liều và companion, **fail nếu có test bị skip**.
- **Mô phỏng local đúng các bước:** DB trống → 66 migration lên `0065` → **123 passed, 0 skip**. Kiểm chiều ngược lại: không có DB thì 21 test skip và bước kiểm tra fail đúng như mong đợi.
- Ghi chú: job `lint-and-test` sẵn có đang chạy `ruff check backend/ tests/`, mà có lỗi lint **có từ trước** trong các file không liên quan (ví dụ `backend/services/telemetry.py`). Không sửa trong task này.

### Runtime production — UNKNOWN (cần operator)

Không có Railway CLI hay quyền truy cập. Operator có quyền chạy (chỉ in đúng một key):

```bash
railway variables --service "VMEC-04/BE" --environment production --kv | grep '^DOSE_RUNTIME_MODE=' || echo "khong dat -> mac dinh legacy"
```

Hoặc vào Railway UI → project VMEC-04 → service `VMEC-04/BE` → Variables → tìm `DOSE_RUNTIME_MODE`. Companion chỉ chạy ở `legacy`/`shadow`; ở `v2` tự tắt.

### Runbook migration staging (chưa áp dụng ở staging)

- Chuỗi: `0063 → 0064 (dose_event.first_reported_at, nullable + partial index) → 0065 (companion, companion_care_day)`; một head duy nhất. Up/down/up đã kiểm trên DB trống (local). `0064` thêm cột nullable, không backfill: chỉ sửa catalog, không viết lại bảng.
- **Cảnh báo:** `railway.json` chạy `python scripts/safe_migrate.py` ở **preDeploy**, nên **deploy nhánh này sẽ tự áp dụng `0064`/`0065`**.
- Các bước cho operator ở staging:
  1. Backup: `pg_dump --format=custom "$STAGING_DATABASE_URL" > capymedi-pre-0064.dump`.
  2. Kiểm tra: `alembic current` phải là `0063`.
  3. `alembic upgrade 0065` (hoặc để preDeploy tự chạy), rồi kiểm `\d dose_event`, `\d companion_care_day`.
  4. Giữ `COMPANION_ENABLED=false` (mặc định).
- **Rollback:** `alembic downgrade 0063` (xoá bảng companion, **mất cột `first_reported_at`**, tức mất dữ kiện báo cáo kể từ lúc deploy), sau đó deploy lại bản trước. Nếu chỉ cần tắt tính năng thì **tắt flag là đủ**, không cần downgrade.

### Đối soát — giới hạn và quy trình thủ công

- Job 15 phút bắt được: báo cáo trong cửa sổ, lịch thay đổi, và người thân duyệt muộn (qua audit). **Giới hạn:** scheduler ngừng lâu hơn `companion_reconcile_lookback_days` (2) thì sót.
- **Mới:** `scripts/companion_reconcile.py --from YYYY-MM-DD --to YYYY-MM-DD [--patient ID] [--apply]`: mặc định dry-run, tối đa 31 ngày, dùng lại `tinh_lai_ngay`, tôn trọng flag/cohort/runtime, chỉ in `patient_id` và ngày. Test: dry-run không ghi; `--apply` bù được liều 6 ngày trước; chạy lại không đổi; khoảng 40 ngày bị từ chối.
- **Giám sát:** cảnh báo khi (a) không thấy dòng log INFO `{"job":"doi_soat_companion",...}` trong hơn 1 giờ, hoặc (b) `recovered_missing > 0` hai lần liên tiếp, hoặc (c) `errors > 0`. Log chỉ có `patient_id` (định danh nội bộ), không có tên hay nội dung y tế.

### QA-02 / QA-04

- **QA-02: PARTIALLY VERIFIED.** Local không có `VLM_API_KEY` (cấu hình `vlm_api_key` để trống), và không có credential test được cấp phép. Đường ảnh khớp mới chỉ chạy qua verifier thật với VLM giả.
- **QA-04: PASS trên trình duyệt** (tài khoản người thân giả, link `accepted`). Khi chờ duyệt: thẻ bệnh nhân hiện ⏳, tiến độ 0%. Người thân duyệt liều D-3 (thành DELAYED) được tính cho D-3 = 100. Duyệt liều hôm nay (TAKEN) cộng từ chối liều kia (MISSED) cho hôm nay = 50 (1/2). Thẻ bệnh nhân sau tải lại: "50% đến Capy con", khớp API và DB.

### Lockfile

`frontend/Dockerfile` ghi rõ repo giữ **cả** `package-lock.json` và `pnpm-lock.yaml`, build **chỉ dùng pnpm**. `pnpm install --frozen-lockfile` cho kết quả "Already up to date". `package-lock.json` đã đồng bộ lại (ở HEAD nó vẫn khớp). Giữ cả hai theo convention hiện có; bỏ `package-lock.json` hay không là quyết định của Tech Lead.

### Test đợt 2 (đã chạy thật)

- Mô phỏng job CI (DB trống): **123 passed, 0 skip**; bước kiểm tra skip phát hiện đúng ca không có DB.
- Đối soát cộng CLI: **8 passed**.
- `pnpm build`: **thành công**. `tsc --noEmit` và `eslint` trên các file đã đổi: sạch.
- Smoke test trình duyệt luồng chính sau khi sửa: không có hồi quy (cho ăn → lớn lên → ack → tải lại không hiện lại lễ).
