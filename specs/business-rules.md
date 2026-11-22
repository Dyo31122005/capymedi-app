# Business Rules — VMEC-04

> **Owner:** PM (Nguyễn Hải Yến) + Architect (Nguyễn Minh Đạt) · **Cập nhật khi:** quy tắc nghiệp vụ thay đổi
> Đây là nơi tập trung **các con số và quy tắc nghiệp vụ cứng** mà code phải tuân theo. Khi implement, AI lấy giá trị từ file này — không tự chọn con số.
> Mọi giá trị ở đây phải khai báo thành **config/constant có tên**, không hardcode rải rác trong code (xem ADR-0004).

## 1. Vòng đời phác đồ (Prescription lifecycle)

```
draft ──(bác sĩ sửa)──> draft
draft ──(bác sĩ DUYỆT)──> approved ──> active ──(hết đợt / bác sĩ dừng)──> completed | stopped
```

| Quy tắc | Nội dung |
|---|---|
| BR-1.1 | Agent **chỉ** hoạt động trên phác đồ `approved`. Phác đồ `draft` không sinh `dose_event`, không nhắc, không chat theo liều. |
| BR-1.2 | Chỉ `doctor` phụ trách bệnh nhân đó mới được duyệt. |
| BR-1.3 | Sửa phác đồ đang chạy → chỉ sinh lại các `dose_event` **chưa tới hạn**; liều đã đóng giữ nguyên lịch sử. |
| BR-1.4 | Dừng phác đồ → mọi `dose_event` `PENDING` chuyển `CANCELLED`, ngừng nhắc ngay. |
| BR-1.5 | Mọi chuyển trạng thái đều ghi `audit_log` kèm actor + thời điểm. |

## 2. Lịch nhắc & dose window

| Tham số | Giá trị | Ghi chú |
|---|---|---|
| Chu kỳ cron quét `dose_event` | **1 phút** | ADR-0007 |
| Độ trễ nhắc tối đa | **< 1 phút** | so với `scheduled_at` |
| Dose window | **±30 phút** quanh `scheduled_at` | tổng 60 phút |
| Số cấp nhắc | **3** | tăng dần về mức độ khẩn |
| Mốc nhắc cấp 1 / 2 / 3 | `T+0` / `T+15'` / `T+30'` `[ĐỀ XUẤT — CẦN CHỐT với PM]` | tính từ `scheduled_at` |
| Đóng window | `window_end` (T+30') | không phản hồi → `MISSED` |
| Biến tăng tốc demo | `TIME_OFFSET_FACTOR` (env) | rút ngắn mọi mốc thời gian khi demo, mặc định `1` |

| Quy tắc | Nội dung |
|---|---|
| BR-2.1 | Bệnh nhân xác nhận ở bất kỳ cấp nào → **huỷ ngay** các cấp nhắc còn lại của liều đó. |
| BR-2.2 | Xác nhận trong window → `TAKEN`. Xác nhận **sau** `window_end` nhưng trong cùng ngày → `DELAYED`, không phải `TAKEN`. |
| BR-2.3 | Sinh `dose_event` phải **idempotent** — duyệt lại/sửa phác đồ không tạo bản ghi trùng. |
| BR-2.4 | Không nhắc liều thuộc phác đồ đã `stopped`/`completed`. |

## 3. Mức nghiêm trọng & escalation

Mức nghiêm trọng được quyết định bởi **loại thuốc + ngữ cảnh RAG**, không phải rule cứng theo số liều bỏ lỡ (FEAT-007).

| Mức | Ví dụ tình huống | Hành động | SLA |
|---|---|---|---|
| **LOW (Nhẹ)** | Bỏ 1 liều vitamin, uống trễ 20 phút | Ghi log, **theo dõi 48h**, không làm phiền ai | — |
| **MEDIUM (Trung bình)** | Bỏ liều thuốc mãn tính; tác dụng phụ nhẹ; ảnh không khớp sau 2 lần | Escalate **người thân + bác sĩ** | `[CẦN CHỐT: đề xuất ≤ 15 phút]` |
| **HIGH (Nghiêm trọng)** | Triệu chứng redflag (khó thở, đau ngực, ngất); bỏ liều thuốc tim mạch/chống đông | **Overlay cấp cứu** cho bệnh nhân + push khẩn người thân & bác sĩ **song song** | **< 2 phút** |

| Quy tắc | Nội dung |
|---|---|
| BR-3.1 | **Bỏ 1 liều thuốc tim mạch nghiêm trọng hơn bỏ 3 liều vitamin** — đây là ví dụ nghiệm thu bắt buộc của FEAT-007. |
| BR-3.2 | Nếu RAG không có thông tin về mức nguy hiểm của thuốc → **nâng lên MEDIUM** (an toàn trước), không hạ xuống LOW. |
| BR-3.3 | Safety layer cờ đỏ → **luôn là HIGH**, ghi đè mọi kết quả đánh giá của luồng chính. |
| BR-3.4 | Gộp cảnh báo trùng trong cùng một dose window để tránh spam người thân. |
| BR-3.5 | Mức HIGH không xếp hàng chờ người thân xử lý trước — gửi thẳng cả người thân và bác sĩ. |
| BR-3.6 | Field `muc_nghiem_trong` trong `data pharmacy/*/thuoc.json` là **prior/fallback**, dùng khi RAG per-thuốc (`tac_dung`) không đủ rõ để quyết — **không thay thế** đánh giá per-thuốc, chỉ nâng lên chứ không hạ thấp mức đã suy ra từ RAG (cùng tinh thần BR-3.2). |

### Mức nghiêm trọng mặc định — đã tính sẵn theo từng thuốc *(cập nhật 2026-08-04)*

Ban đầu định làm bảng fallback theo **11 thư mục** (`data pharmacy/`), nhưng quá thô — 1 thư mục lớn như "Thuốc tim mạch và máu" gộp chung cả thuốc chống đông (rất nguy hiểm) lẫn thuốc trị trĩ/suy giãn tĩnh mạch (nhẹ hơn nhiều). Thay vào đó, mỗi thuốc đã có sẵn field **`muc_nghiem_trong`** (`Nhẹ` / `Trung bình` / `Nguy hiểm`), tính rule-based (không LLM) qua [`scripts/classify_severity.py`](../scripts/classify_severity.py) — tra theo `danh_muc` (**52 tiểu mục gốc của trang nguồn**, chi tiết hơn nhiều 11 thư mục, vd tách riêng "Thuốc chống đông máu" khỏi "Thuốc trị trĩ, suy giãn tĩnh mạch"). Xem bảng tra cứu đầy đủ + lý do từng nhóm ngay trong file script đó — không lặp lại ở đây để tránh 2 nguồn dễ lệch nhau.

**Số liệu hiện tại** (3688 thuốc, 11 thư mục, chạy `classify_severity.py --report-only` để xem lại): **1398 Nguy hiểm · 1403 Trung bình · 887 Nhẹ**.

**Ví dụ ngoại lệ đã xử lý ở mức tiểu mục:** glaucoma/tăng nhãn áp được site tự tách thành tiểu mục riêng "Thuốc trị tăng nhãn áp" (khác "Thuốc nhỏ mắt" thông thường) nên tự nhiên có mức riêng (Trung bình), không lẫn vào mức Nhẹ của nhóm nhỏ mắt nói chung — không cần rule ngoại lệ thủ công.

## 4. Xác nhận bằng ảnh

| Tham số | Giá trị |
|---|---|
| Số lần chụp lại tối đa | **2** |
| Sau 2 lần không khớp | Chuyển **người thân duyệt** |
| SLA người thân duyệt | **1 giờ** |
| Quá SLA người thân | `[CẦN CHỐT: đề xuất → MISSED + escalate MEDIUM]` |

| Quy tắc | Nội dung |
|---|---|
| BR-4.1 | `TAKEN (có xác minh bằng ảnh)` và `TAKEN (tự khai bằng nút bấm)` là **hai trạng thái khác nhau**, không được gộp trên dashboard bác sĩ. |
| BR-4.2 | Ảnh luôn lưu kèm `detected_count`, `expected_count`, `confidence` vào audit log. |
| BR-4.3 | Ảnh là dữ liệu PHI → lưu có kiểm soát truy cập, không commit vào repo, không đưa vào log dạng plain. |
| BR-4.4 | *(TASK-CAPY-27)* Nhận diện ảnh (đúng thuốc/đúng số viên) **không chứng minh bệnh nhân đã uống**. Gửi ảnh xác nhận liều = bệnh nhân **tự xác nhận đã uống**; UI phải nói rõ điều này ngay trước nút gửi ("Gửi ảnh & xác nhận đã uống"). Hệ thống không bao giờ chốt `TAKEN` chỉ từ kết quả OCR. |
| BR-4.5 | *(TASK-CAPY-27)* Kết quả xác minh ảnh công khai là `MATCHED` / `MISMATCHED` / `UNCERTAIN`; khi `UNCERTAIN` phải kèm lý do (`UNKNOWN`, `UNCERTAIN`, `INSUFFICIENT_IMAGE`, `MULTIPLE_CANDIDATES`, `SYSTEM_ERROR`). Quyết định vẫn do bộ đối chiếu số lượng theo dạng bào chế (ADR-0011); OCR tên/hàm lượng chỉ là bằng chứng tư vấn cho tới khi có eval (ADR-0004 §10). |
| BR-4.6 | *(TASK-CAPY-27)* Ảnh không đạt chất lượng tối thiểu (quá nhỏ/tỉ lệ cực đoan) bị từ chối **trước** khi gọi VLM, không trừ lượt chụp, câu báo: "Chưa đọc rõ thông tin thuốc. Vui lòng thử chụp gần hơn hoặc chụp mặt có tên thuốc." |

## 5. Phân loại hội thoại

| Tham số | Giá trị |
|---|---|
| Tập nhãn | `TAKEN` · `MISSED` · `DELAYED` · `SIDE_EFFECT` |
| Ngưỡng confidence để chấp nhận nhãn | `0.7` `[ĐỀ XUẤT — CẦN CHỐT sau khi có test set]` |
| Dưới ngưỡng | Agent **hỏi lại**, không tự đoán |
| Số lần hỏi lại tối đa | `[CẦN CHỐT: đề xuất 2, sau đó ghi UNKNOWN + để người thân xem]` |

| Quy tắc | Nội dung |
|---|---|
| BR-5.1 | Một phát ngôn có thể có nhãn phụ (VD: `TAKEN` + `SIDE_EFFECT`) — phải phát hiện tác dụng phụ **ẩn** trong câu nói. |
| BR-5.2 | Mọi phát ngôn đi qua safety layer **song song**, độc lập với luồng phân loại này. |
| BR-5.3 | Agent **không** trả lời câu hỏi mang tính chẩn đoán/kê đơn — chuyển hướng sang bác sĩ. |

## 6. Safety layer

| Quy tắc | Nội dung |
|---|---|
| BR-6.1 | Kết hợp **keyword rules OR LLM** — chỉ cần **một** lớp cờ đỏ là kích hoạt. |
| BR-6.2 | Mục tiêu **recall ≥ 90–95%**; chấp nhận false positive (báo thừa còn hơn bỏ sót). |
| BR-6.3 | Safety layer không được bị chặn bởi lỗi/timeout của luồng chính; nếu LLM lỗi → **vẫn chạy keyword layer**. |
| BR-6.4 | Danh sách keyword redflag lưu thành file versioned trong repo, sửa được không cần đổi code. |
| BR-6.5 | Không role nào (kể cả `admin`) được tắt safety layer từ UI. |
| BR-6.6 | Redflag chia **2 nhóm** (xem dưới): *triệu chứng lâm sàng* (đang xảy ra, cần cấp cứu ngay) và *nguy cơ liều dùng bất thường* (có thể là hỏi trước khi hành động — vẫn phải chặn ở mức HIGH, không chờ xác nhận đã uống hay chưa). |

**Nhóm 1 — Triệu chứng lâm sàng** (mở rộng ở TASK-008): khó thở · đau ngực · ngất/xỉu · co giật · nôn ra máu · yếu liệt nửa người · nói khó/méo miệng · lú lẫn đột ngột · chảy máu không cầm · dị ứng nặng (sưng mặt/môi, nổi mề đay toàn thân).

**Nhóm 2 — Nguy cơ liều dùng bất thường / quá liều** *(bổ sung 2026-08-04, phát hiện khi thảo luận thiết kế chatbot RAG — chưa có trong bản gốc Gate 01)*: bệnh nhân hỏi/nói về việc dùng **số lượng thuốc lớn bất thường so với liều đã kê**, hoặc có dấu hiệu ý định dùng sai mục đích — ví dụ: "tôi có 10 viên thuốc ngủ, uống hết được không", "uống gấp đôi/gấp ba liều có sao không", "uống hết cả vỉ có làm sao không". Khác nhóm 1 ở chỗ đây là **hỏi trước khi hành động**, không phải triệu chứng đã xảy ra — nhưng vẫn phải xử lý ở mức **HIGH ngay lập tức**, không chờ xem bệnh nhân có thực sự uống hay không.

| Quy tắc | Nội dung |
|---|---|
| BR-6.7 | Redflag nhóm 2 kích hoạt khi phát ngôn có **số lượng thuốc** (số viên/liều) kèm ngữ cảnh hỏi/định dùng, không cần so khớp được với đúng thuốc nào trong phác đồ — an toàn trước, làm rõ sau. |
| BR-6.8 | `[CẦN CHỐT — PM + Phạm Thành Đạt]` nội dung overlay cho nhóm 2 nên khác nhóm 1 (vd hướng dẫn liên hệ Trung tâm chống độc thay vì cấp cứu tổng quát) — cần xác nhận trước khi viết prompt/overlay UI. |

Cả 2 nhóm đều dùng chung cơ chế `keyword rules OR LLM` (BR-6.1) — nhóm 2 khó phủ hết bằng keyword đơn thuần (nhiều cách diễn đạt số lượng) nên **phụ thuộc nhiều hơn vào lớp LLM**; cần ưu tiên nhóm 2 khi xây bộ test set TASK-008 để đo riêng recall của nó.

## 7. Ràng buộc an toàn tuyệt đối (agent KHÔNG được làm)

| Quy tắc | Nội dung |
|---|---|
| BR-7.1 | Agent **không kê đơn, không đổi thuốc, không đổi liều, không chẩn đoán**. |
| BR-7.2 | Mọi đề xuất đổi lịch nhắc phải **chờ bác sĩ duyệt**, agent không tự áp dụng (ADR-0010). |
| BR-7.3 | Agent **không khẳng định thông tin thuốc khi không có nguồn RAG** — phải nói "không có thông tin, vui lòng hỏi bác sĩ". |
| BR-7.4 | Agent không thay thế cấp cứu — khi HIGH, hiển thị hướng dẫn liên hệ cấp cứu, không tự xử lý y khoa. |
| BR-7.5 | Bản ghi `audit_log` là **append-only** — không sửa, không xoá. |

## 8. Ghi nhận liều trễ & tiến độ Capybara Companion — `PROPOSED`, chưa có hiệu lực

> Thêm 2026-11-14 theo [ADR-0016](../adrs/0016-capybara-companion-domain.md). **Chưa có hiệu lực** cho tới khi được duyệt. Mục 8.1 và các quy tắc LP/SP ở 8.2 là thay đổi nghiệp vụ lâm sàng / kinh tế điểm. Code phải để các giá trị dưới đây ở dạng hằng số có tên, và các quy tắc 8.1 nằm sau quyết định duyệt, không được tự bật.

### 8.1 Ghi nhận lịch sử uống thuốc (domain `scheduling`)

| Quy tắc | Nội dung | Duyệt |
|---|---|---|
| BR-8.1 | `PATCH /doses/{id}` chỉ nhận `TAKEN` hoặc `MISSED`. `CANCELLED` chỉ được sinh khi dừng phác đồ (BR-1.4); `PENDING`, `DELAYED` và `AWAITING_CAREGIVER` chỉ do hệ thống đặt. | Tech Lead |
| BR-8.2 | Bệnh nhân, và người thân có link `accepted`, được ghi `TAKEN`/`MISSED` cho liều có ngày hẹn ∈ `[hôm nay − LATE_REPORT_DAYS, hôm nay]`. Ngoài khoảng đó trả 422. Bác sĩ không bị giới hạn ngày. Người thân hoặc bác sĩ duyệt một liều `AWAITING_CAREGIVER` thì không bị giới hạn ngày. | **PM + bác sĩ** |
| BR-8.3 | Whitelist chuyển trạng thái: `PENDING→{TAKEN,MISSED}`, `MISSED→TAKEN`, `TAKEN→MISSED` (trong khoảng BR-8.2), `AWAITING_CAREGIVER→{TAKEN,MISSED}` (chỉ người thân hoặc bác sĩ). Gửi lại đúng trạng thái hiện tại là **no-op**: không suy lại DELAYED, không cộng lại điểm. | Tech Lead |
| BR-8.4 | Báo cáo trễ vẫn suy ra TAKEN/DELAYED theo BR-2.2 (không đổi). "Báo cáo trễ" nghĩa là ngày địa phương của `first_reported_at` lớn hơn ngày hẹn. | PM |
| BR-8.5 | `dose_event.first_reported_at` = thời điểm server ghi nhận **lần đầu** liều chuyển sang `TAKEN`, `DELAYED` hoặc `AWAITING_CAREGIVER`. Ghi một lần, không ghi đè, không backfill. | Tech Lead |
| BR-8.6 | Mọi PATCH có thay đổi trạng thái đều ghi `system_audit_logs` (actor, from, to, cờ trễ), không chứa PHI (BR-1.5). | Tech Lead |

### 8.2 Điểm thưởng và tiến độ Capy

| Quy tắc | Nội dung | Duyệt |
|---|---|---|
| BR-8.7 | Báo cáo khác ngày (BR-8.4) nhận **0 LP/SP**. Mức trừ tự khai (`PCT_SELF_REPORT_NO_PHOTO`) được xác định theo **người gọi và bằng chứng**, không theo trạng thái trước đó. | **Tech Lead** (thay đổi kinh tế điểm) |
| BR-8.8 | Tiến độ Capy độc lập hoàn toàn với LP/SP và với tuân thủ lâm sàng. Không quy đổi, không hiển thị con số đơn vị cho người dùng. | PO |
| BR-8.9 | Mỗi ngày: `units = floor(DAY_UNITS × k / n)`. `n` là số slot không bị `CANCELLED` trong ngày; `k` là số slot đang `TAKEN` hoặc `DELAYED` có `first_reported_at` cùng ngày địa phương với ngày hẹn. Lưu bằng `GREATEST` (chỉ tăng). | PO |
| BR-8.10 | `AWAITING_CAREGIVER` chưa được tính tiến độ; người thân duyệt `TAKEN` thì được tính cho ngày hẹn. Ảnh không khớp đơn thuốc **không bao giờ** có màn ăn mừng cho Capy ăn. | PO |
| BR-8.10b | Liều TAKEN **chỉ do fallback** "ảnh sai hết lượt, không có người thân" (có ảnh, không ảnh nào khớp, không có xác nhận rõ ràng trong audit) **không** được tính tiến độ Capy. Hồ sơ lâm sàng và LP/SP giữ nguyên chính sách hiện có. Bệnh nhân bấm "Tôi đã uống thuốc này" thì đó là xác nhận rõ ràng (audit `DOSE_EXPLICIT_CONFIRM`) và Capy được tính như tự khai (TASK-CAPY-26). | PO (đã chỉ đạo) |
| BR-8.11 | Capy không bao giờ đói, ốm, buồn hay mất tiến độ vì bỏ liều. Câu chữ không bao giờ gợi ý uống bù. | PO |

| Hằng số | Giá trị đề xuất | Trạng thái |
|---|---|---|
| `LATE_REPORT_DAYS` | 3 | `[CẦN CHỐT: PM + bác sĩ]` |
| `COMPANION_DAY_UNITS` | 100 | Đề xuất |
| `COMPANION_STAGE_THRESHOLDS` | 0 / 300 / 1400 / 4200 (ứng với 3 / 14 / 42 ngày chăm sóc) | Đề xuất, PO duyệt |
| `COMPANION_RECONCILE_MINUTES` | 15 | Đề xuất |

---
**Lưu ý cho AI:** Mọi con số trong file này phải xuất hiện trong code dưới dạng **hằng số có tên / biến config** (VD: `DOSE_WINDOW_MINUTES = 30`), không rải magic number. Nếu task yêu cầu một giá trị chưa có ở đây hoặc đang là `[CẦN CHỐT]` → **hỏi PM**, không tự chọn.
