# ADR-0016: Domain `companion` — Capybara Companion

**Status:** Proposed
**Ngày:** 2026-11-14
**Người đề xuất:** AI (Claude Code) theo yêu cầu Product Owner
**Người duyệt:** `[chờ Tech Lead + PM; D-7 cần thêm bác sĩ, D-13 cần Tech Lead]`

## Bối cảnh (Context)

Product Owner muốn biến mỗi lần xác nhận liều thuốc thành một khoảnh khắc chăm sóc: bệnh nhân "cho Capy ăn", và Capy lớn dần theo những ngày bệnh nhân giữ được nếp uống thuốc. Kế hoạch đầy đủ nằm ở [`../planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md) (bản R2).

Tính năng này chạm tới ba chỗ nhạy cảm, nên cần một quyết định kiến trúc thành văn:

1. **Trạng thái liều là dữ liệu lâm sàng.** `PATCH /doses/{id}` ở runtime legacy hiện nhận mọi chuỗi status ([`backend/api/dose_routes.py`](../backend/api/dose_routes.py), `DoseStatusUpdateRequest.status: str`), không ghi audit, và cho phép xác nhận lùi ngày mà vẫn được cộng điểm (lỗ hổng V-1 đến V-6 trong kế hoạch).
2. **Hệ thống điểm LP/SP đã quy đổi được ra quà thật** ([`backend/services/reward_catalog.py`](../backend/services/reward_catalog.py)). Thêm một đơn vị thưởng mới sẽ gây nhầm lẫn và mở thêm đường lạm dụng.
3. **Có hai runtime liều** (`legacy`/`shadow` phục vụ từ `dose_event`, còn `v2` từ `dose_occurrence`). Giá trị ở production chưa xác minh được (blocker B-1).

## Quyết định (Decision)

1. **Thêm domain `companion`**, sở hữu bảng `companion` và `companion_care_day`. Domain này **không đọc và không ghi** LP/SP (`reward`), và không thay đổi công thức tuân thủ lâm sàng (`reporting`).
2. **Tiến độ tính theo "ngày chăm sóc":** mỗi ngày lịch tối đa 100 đơn vị nội bộ, tính bằng `floor(100 × k / n)`.
   - `n` là số slot của ngày đó không bị `CANCELLED`.
   - `k` là số slot đang TAKEN hoặc DELAYED và có báo cáo lần đầu trong cùng ngày địa phương.
   - Ngưỡng giai đoạn: 300 / 1400 / 4200.
   - Người dùng không bao giờ thấy con số đơn vị, chỉ thấy tên giai đoạn và %.
3. **Mọi lần ghi tiến độ đi qua một hàm tất định** `tinh_lai_ngay(patient, ngày)`. Hàm khoá dòng `companion` (`FOR UPDATE`), đếm lại từ `dose_event`, rồi upsert với `GREATEST` (chỉ tăng). Có hai bên gọi:
   - hook trong `PATCH /doses/{id}` và `verifier.py`, chạy trong savepoint nên lỗi không chặn việc ghi liều;
   - job đối soát mỗi 15 phút, tính lại hôm qua và hôm nay.

   `GET /companion/me` là đọc thuần, không có tác dụng phụ.
4. **Domain `scheduling` thêm cột `dose_event.first_reported_at`:** thời điểm server ghi nhận lần đầu liều chuyển sang TAKEN, DELAYED hoặc AWAITING_CAREGIVER. Ghi một lần, không ghi đè, không backfill. Đây là dữ kiện lâm sàng, và cũng là căn cứ để kiểm tra điều kiện "cùng ngày" của companion.
5. **Ghi nhận lâm sàng tách khỏi điều kiện nhận thưởng:**
   - Bệnh nhân được báo cáo trễ trong `LATE_REPORT_DAYS` ngày.
   - Báo cáo khác ngày nhận 0 LP/SP và không làm Capy lớn, nhưng **vẫn được ghi vào hồ sơ**.
   - PATCH chỉ nhận `TAKEN`/`MISSED`, đi theo whitelist chuyển trạng thái, và có audit.
6. **Màn ăn mừng là quyết định của client, tách khỏi điều kiện lớn lên ở server.**
   - Ảnh không khớp đơn thuốc không bao giờ được ăn mừng.
   - AWAITING_CAREGIVER chưa được tính cho tới khi người thân duyệt TAKEN.
7. **Companion tự tắt ở runtime `v2`** cho tới khi có task hỗ trợ V2 (TASK-CAPY-30).

## Vì sao (Rationale)

**Phương án đã cân nhắc và loại bỏ:**

- **Suy ra tiến độ Capy từ LP.** Bị loại vì LP có thưởng chuỗi kiểu vách đá và trọng số theo giờ uống. Capy sẽ thừa hưởng áp lực đó và dính vào nền kinh tế quà thật.
- **Chuẩn hoá theo tuần.** Bị loại vì một liều thuốc tuần sẽ nhảy giai đoạn ngay, đợt điều trị ngắn lớn nhanh hơn, và tuần không trọn vẹn bị thổi phồng.
- **Ghi credit theo từng slot dựa trên `now` trong bộ nhớ (bản R1).** Bị loại vì không phục hồi được khi hook lỗi, và tính thiếu khi bác sĩ huỷ liều trong ngày.
- **Tính và ghi trong `GET`.** Bị loại vì vi phạm tính an toàn của GET. Repo cũng chưa từng làm vậy: `reward_ledger.get_summary` là đọc thuần.
- **Chỉ cho bệnh nhân xác nhận liều trong ngày.** Bị loại vì làm sai hồ sơ y tế: người uống đúng giờ nhưng quên ghi sẽ bị kẹt ở MISSED.
- **Tính AWAITING ngay và ăn mừng mọi xác nhận.** Bị loại vì ảnh không khớp có thể là uống nhầm thuốc, và vì cách đó mở đường "gửi 3 ảnh sai để được tính".

## Vì sao thân thiện với AI + Team

- Mọi lần ghi tiến độ đi qua đúng một hàm, nên agent biết chính xác chỗ cần sửa và chỗ cần test.
- Ranh giới `companion` / `reward` / `reporting` tách bạch, không domain nào đọc chéo dữ liệu của domain khác.
- Hàm tính là hàm thuần trên dữ liệu DB, test được bằng SQLite mà không cần dựng app.

## Hệ quả (Consequences)

**Tích cực:**
- Bệnh nhân uống 1 hay 4 liều/ngày lớn như nhau. Không sự kiện đơn lẻ nào làm nhảy giai đoạn. Ngày nghỉ thuốc không bị trừ gì.
- Hook lỗi được job phục hồi trong tối đa 15 phút, có log WARNING `recovered_missing`.
- Đóng được các lỗ hổng V-1 đến V-6 của `PATCH /doses`.

**Đánh đổi / rủi ro:**
- Tính dư có giới hạn khi bác sĩ tăng liều giữa ngày (T-1), và khi bệnh nhân sửa TAKEN thành MISSED sau khi đã được tính (T-3). Chi tiết ở §4.7 của kế hoạch.
- Thêm một job nền và một migration chạm vào `dose_event`.
- **Cần duyệt nghiệp vụ trước khi bật:** `LATE_REPORT_DAYS` (PM + bác sĩ); quy tắc 0 LP/SP cho báo cáo khác ngày và mức trừ theo người gọi (Tech Lead).
- Runtime ở production chưa xác minh được (B-1). Không bật flag cho tới khi xác minh xong.

## Câu chốt

> Capy lớn theo những ngày bạn chăm sóc mình, chứ không theo số viên thuốc. Hồ sơ y tế luôn được ghi đúng, kể cả khi Capy không được tính.
