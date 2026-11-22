# ADR-0017: Agent V2 MVP — model chính, tra web làm nguồn, chính sách grounding và lớp an toàn

**Status:** Accepted (MVP / demo) cho quyết định 1–4 (Agent/RAG). Phần an toàn (quyết định 4–5 và việc bỏ escalate cụm nói quá "mệt/đói muốn chết") chờ reviewer Safety.
**Ngày:** 2026-11-14
**Người đề xuất:** MustelaFerret (chủ chatbot Agent V2)
**Người duyệt:** Nguyễn Minh Đạt (reviewer Agent/RAG theo TEAM.md) duyệt quyết định 1–4 ngày 2026-11-14. Chờ Phạm Thành Đạt (reviewer Safety) duyệt phần an toàn.

## Bối cảnh (Context)

Review nhánh `feature/chatbot-natural-tone-v2` (issue #9) yêu cầu chốt bằng ADR các quyết định đã đưa vào code mà chưa có văn bản (AGENTS.md §9):

1. Đổi `agent_main_model` từ `gpt-5.4-mini` sang `gpt-5.6-luna`.
2. Dùng web search (OpenAI hosted) làm nguồn dữ kiện thuốc khi dữ liệu nội bộ không có.
3. `agent_strict_general_grounding=False` mặc định.
4. `agent_semantic_safety_enabled=True`, tức thêm một lần gọi mô hình cho mỗi tin nhắn.

Mục tiêu hiện tại là MVP và demo cho pitching: chatbot trả lời tự nhiên, đúng việc cốt lõi (lịch thuốc, đơn thuốc, thông tin thuốc), và không làm yếu lớp an toàn.

## Quyết định (Decision)

| # | Quyết định | Cấu hình |
|---|---|---|
| 1 | Model chính là `gpt-5.6-luna`, không bật reasoning. | `AGENT_MAIN_MODEL=gpt-5.6-luna`, `AGENT_MAIN_REASONING_EFFORT=none` |
| 2 | Khi danh mục thuốc và tờ hướng dẫn nội bộ không có câu trả lời, tra web và **coi kết quả là nguồn đáng tin**. Chỉ tra trong danh sách tên miền y tế, và luôn hiện nguồn kèm câu trả lời. | `AGENT_WEB_SEARCH_ENABLED=true`, `agent_web_search_domains` |
| 3 | Câu hỏi sức khỏe phổ thông, ít rủi ro được trả lời mà không cần bằng chứng từ tool. **Dữ kiện cụ thể về thuốc thì vẫn bắt buộc có bằng chứng** (tờ hướng dẫn hoặc web). | `AGENT_STRICT_GENERAL_GROUNDING=false` (mặc định) |
| 4 | Bật lớp phân loại an toàn ngữ nghĩa. Lớp này **chỉ được nâng mức, không được hạ**; lỗi hoặc quá giờ thì giữ quyết định từ khoá. | `AGENT_SEMANTIC_SAFETY_ENABLED=true` |
| 5 | Bậc B3 (câu check-in cho "buồn/đau muốn chết" và lời khẩn cấp theo từng loại nguy hiểm) **tắt** cho tới khi bác sĩ duyệt. Khi tắt, mọi lời khẩn cấp dùng đúng văn bản đang chạy trên main. | `AGENT_SAFETY_B3_ENABLED=false` (mặc định) |

## Vì sao (Rationale)

1. **luna:** rẻ hơn khoảng 3,75 lần mỗi token so với `gpt-5.4-mini` theo bảng giá chính thức (kiểm tra ngày 2026-11-14). Ở mức `none`, độ trễ đo được tương đương. Phương án giữ `gpt-5.4-mini` bị loại vì chi phí.
2. **Tra web:** danh mục nội bộ không phủ hết thuốc và câu hỏi. Từ chối thẳng ("mình chưa có thông tin") làm hỏng trải nghiệm demo. Phương án tự crawl Vinmec bị loại: mất 15–21 giây mỗi câu và luôn ra 0 kết quả.
3. **Grounding linh hoạt:** chế độ nghiêm làm bot từ chối cả những câu vô hại như mẹo nhớ uống thuốc hay ăn uống cho người tăng huyết áp. Nghĩa vụ grounding vẫn giữ ở chỗ rủi ro thật là dữ kiện thuốc.
4. **Phân loại ngữ nghĩa:** lớp từ khoá không bắt được mọi cách nói ("chán sống quá" trước đây không được coi là khẩn cấp). Chi phí khoảng 0,14 USD cho 1000 lượt.
5. **B3 tắt:** văn bản khẩn cấp đưa tới bệnh nhân thật phải được bác sĩ duyệt (issue #9, lỗi chặn 2 và 5).

## Vì sao thân thiện với AI + Team

- Mọi lựa chọn đều là biến môi trường có giá trị mặc định ghi trong `backend/config.py` và `.env.example`, nên đổi lại không cần sửa code.
- Phần chưa được duyệt lâm sàng nằm sau một cờ duy nhất, dễ kiểm tra và dễ bật khi đã duyệt.

## Hệ quả (Consequences)

**Tích cực:**
- Bot trả lời được nhiều câu hơn, có nguồn rõ ràng; chi phí mô hình giảm.
- Lớp từ khoá không yếu hơn main; lớp ngữ nghĩa bổ sung thêm.

**Đánh đổi / rủi ro:**
- Danh sách tên miền có cả nhà thuốc bán lẻ (nhathuoclongchau) và trang nội dung (hellobacsi). Trước khi lên production cần chốt lại danh sách nguồn.
- Mỗi tin nhắn thêm khoảng 1–4 giây chờ bộ phân loại (chạy song song khi có thể).
- Câu trả lời từ web không được duyệt trước. Đây là đánh đổi có chủ đích của MVP, cần xem lại trước khi phục vụ bệnh nhân thật.

## Câu chốt

> MVP ưu tiên trả lời được và tự nhiên. Dữ kiện thuốc vẫn phải có nguồn, và an toàn chỉ được nâng chứ không được hạ.
