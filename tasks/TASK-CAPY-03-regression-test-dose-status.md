# TASK-CAPY-03: Regression test baseline cho V-1 đến V-6 (`PATCH /doses/{id}`)

**Domain:** `scheduling`, `reward`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** Done

## Mục tiêu (Goal)

Viết test tái hiện các lỗ hổng V-1 đến V-6 của `PATCH /doses/{id}` (runtime legacy), mô tả trong §2.2 của kế hoạch. **Không sửa backend trong task này.** Test được kỳ vọng **đỏ** trên code hiện tại; TASK-CAPY-08 sẽ làm chúng xanh.

## Acceptance Criteria (AC)

- [x] `tests/test_api/test_dose_status_rules.py`: mỗi lỗ hổng V-1 đến V-6 có ít nhất một test, assert **hành vi mong muốn** sau khi sửa (7 test).
- [x] Đã chạy `pytest tests/test_api/test_dose_status_rules.py -q` **trên Postgres thật** và ghi lại kết quả thật bên dưới.
- [x] Không sửa file ứng dụng nào.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] `backend/api/dose_routes.py`, `backend/services/dose_lifecycle.py`, `backend/services/reward_ledger.py`
- [ ] Các pattern test hiện có trong `tests/test_api/`

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md), **trừ** mục "test pass": test đỏ là chủ đích của task này. **Không merge riêng task này vào `main` khi test còn đỏ** (CI sẽ fail). Gộp vào PR cùng TASK-CAPY-08.

## Ghi chú / trao đổi thêm

**2026-11-14 — đã viết, CHƯA CHẠY.**

| Test | Lỗ hổng | Dự đoán trên code hiện tại (theo đọc code, chưa kiểm chứng) |
|---|---|---|
| `test_v1_status_ngoai_taken_missed_bi_tu_choi` | V-1 | Đỏ: trả 200 và ghi `KHONG_HOP_LE` vào DB |
| `test_v2_benh_nhan_khong_tu_dat_cancelled` | V-2 | Đỏ: trả 200, status thành `CANCELLED` |
| `test_v3_missed_roi_taken_tru_dung_cho_va_dung_muc` | V-3 | Đỏ: bấm MISSED đã bị ghi phạt −10 SP; MISSED→TAKEN báo `points_awarded` = 20 thay vì 10 |
| `test_v4_bao_cao_ngoai_khoang_cho_phep_bi_tu_choi` | V-4 | Đỏ: trả 200 (DELAYED) và cộng điểm cho ngày cũ |
| `test_v4_bao_cao_tre_trong_khoang_duoc_ghi_nhung_khong_cong_diem` | V-4 | Đỏ: `points_awarded > 0` |
| `test_v5_gui_lai_taken_la_no_op` | V-5 | Đỏ: retry hạ TAKEN thành DELAYED |
| `test_v6_doi_trang_thai_ghi_audit` | V-6 | Đỏ: không có dòng `system_audit_logs` |

**Đã kiểm chứng:** chỉ `python3 -m py_compile` (cú pháp OK). Chưa chạy được `ruff` (chưa cài).

**Blocker môi trường:** máy dev chưa có `pytest` và dependency Python (không có venv), cũng không có Postgres đang chạy. Có Docker. Lệnh để chạy, **cần người dùng cho phép cài đặt**:

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
docker compose up -d db
export DATABASE_URL=postgresql://vmec:vmec@localhost:5432/vmec04 APP_ENV=test JWT_SECRET=test-jwt INTERNAL_AUTH_SECRET=test-internal OPENAI_API_KEY=test-key
alembic upgrade head
pytest tests/test_api/test_dose_status_rules.py -q
```

**Phát hiện thêm:**
1. **[OBSERVED]** Job `lint-and-test` của CI không có service Postgres (`.github/workflows/ci.yml`, comment ở dòng 72–75). File này, và cả `tests/test_dose_status_update.py`, sẽ bị **SKIP trên CI**. "Xanh trên CI" vì thế không phải bằng chứng; phải chạy trên Postgres thật.
2. **[INFERRED, sửa mô tả V-3]** Bấm "Bỏ qua liều này" (PENDING→MISSED) bị ghi phạt tự khai ngay, dù không được cộng gì, nên SP có thể âm. Tổng ròng sau MISSED→TAKEN vẫn là 10, nhưng màn hình báo "+20" và khoản phạt nằm sai chỗ.
3. Test V-4 dùng liều cách 10 ngày, để không phụ thuộc vào giá trị `LATE_REPORT_DAYS` (vẫn chờ PM + bác sĩ chốt).

**2026-11-14 — ĐÃ CHẠY trên Postgres thật (baseline):** 7 failed, đúng như dự đoán, và **cả 7 fail vì lỗ hổng**, không phải vì setup: V-1/V-2 trả 200 thay vì 422; V-3 bấm MISSED bị ghi `−10` SP; V-4 trả 200 và tạo 1 dòng cộng điểm; V-5 TAKEN thành DELAYED; V-6 có 0 dòng audit. Sau TASK-CAPY-08: 7 passed. Hai test V-4 bật `dose_provisional_policy_enabled` qua fixture `chinh_sach_tam`.
