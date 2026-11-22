# Team Roster & Quyền trên Repo

> **Owner:** PM (Nguyễn Hải Yến) · **Cập nhật khi:** có thay đổi thành viên, phân công, hoặc quyền merge
> File này trả lời **"ai đang làm gì"** và **"ai có quyền gì trên repo"** — cụ thể, có tên thật. Khác với `AGENTS.md` §3 (chỉ định nghĩa vai trò chung chung, không đổi theo từng dự án), file này đổi theo từng team và phải luôn được điền đầy đủ trước khi bắt đầu Sprint đầu tiên.

**Team:** P-067 (G14 - T067) — dự án VMEC-04: AI Agent Nhắc Thuốc & Theo Dõi Tuân Thủ Điều Trị

## 1. Thành viên & phân công

Nhóm 4 người thường kiêm nhiệm nhiều vai trò — điền hết vai trò một người đảm nhận, không để trống. Xem định nghĩa từng vai trò ở `AGENTS.md` §3.

| Tên | Vai trò (PM/Architect/Dev/QA/Ops — có thể kiêm nhiều) | Domain / phụ trách chính | Backup khi vắng | Liên hệ (Slack/email) |
|---|---|---|---|---|
| Nguyễn Minh Đạt<br>`2A202601142` | Team Leader · Architect · Dev (Data/AI) | Data thuốc & RAG (pgvector), LangGraph agent, đánh giá mức nghiêm trọng | Phạm Thành Đạt | [điền Slack/email] |
| Nguyễn Hải Yến<br>`2A202601604` | PM · Designer · Dev (Frontend) | Backlog & Sprint, UI-UX (Figma), FE bác sĩ (web) + bệnh nhân (PWA) | Trương Quốc Trường | [điền Slack/email] |
| Phạm Thành Đạt<br>`2A202601672` | Dev (AI/Fullstack) · QA/Tester | Safety layer, phân loại hội thoại 4 nhãn, test suite & quality gate | Nguyễn Minh Đạt | [điền Slack/email] |
| Trương Quốc Trường<br>`2A202601195` | Tech Leader · Dev (Fullstack) · Ops | Backend FastAPI, scheduler `dose_event`, Git workflow, CI/CD (ruff + pytest) | Nguyễn Minh Đạt | [điền Slack/email] |

## 2. Quyền merge trên repo

- **Merger chính (main maintainer):** Trương Quốc Trường — người mặc định có quyền bấm merge PR vào `main` (chốt tại WORKLOG 2026-07-26, PR review qua Trường).
- **Merger backup:** Nguyễn Minh Đạt (Team Leader) — merge thay khi merger chính vắng mặt quá [X ngày], phải báo trước trong [kênh liên lạc, vd. Slack #team].
- **Số lượng approve tối thiểu trước khi merge:** [1 / 2 — team chưa chốt, cần quyết trước Sprint 2]
- **Reviewer bắt buộc theo domain** (đối chiếu `/specs/domains.md` — **file này chưa tồn tại**, bảng dưới đang tạm suy ra từ phân công ở mục 1 và Tech Stack trong `README.md`; cập nhật lại khi có `domains.md`):

  | Domain | Reviewer bắt buộc |
  |---|---|
  | AI Agent / LangGraph / RAG (`src/agents/`) | Nguyễn Minh Đạt |
  | Safety layer & phân loại hội thoại | Phạm Thành Đạt |
  | Backend API / scheduler / DB (`src/api/`, `src/services/`) | Trương Quốc Trường |
  | Frontend (web bác sĩ, PWA bệnh nhân, mobile người thân) | Nguyễn Hải Yến |
  | DevOps / CI-CD / Docker | Trương Quốc Trường |
  | Tài liệu sản phẩm (BRIEF, PRD, specs) | Nguyễn Hải Yến |

## 3. Luật làm việc trên repo (cụ thể hoá `AGENTS.md` §5)

- Không ai được tự merge PR của chính mình, kể cả merger chính — trừ trường hợp [ngoại lệ nếu có, vd. hotfix production khẩn cấp, phải note lại lý do trong PR].
- Branch protection trên `main`: bắt buộc qua PR + đủ số approve ở mục 2 + CI pass, không cho push thẳng (cấu hình ở Settings của GitHub/GitLab/Bitbucket).
- Khi 2 người cùng đụng vào một domain cùng lúc: [quy tắc giải quyết, vd. người mở PR trước giữ quyền merge trước, người sau rebase].
- Khi merger chính và backup đều vắng: [quy tắc dự phòng, vd. PM chỉ định tạm thời / không merge cho tới khi có người].

### Uỷ quyền merge cho AI (thêm 2026-11-14)

Chỉ áp dụng cho repo cá nhân **`Dyo31122005/capymedi`** (bản tách ra sau khi project Railway bị xoá; hiện chỉ Nguyễn Minh Đạt duy trì). **Không** áp dụng cho repo team `AI20K-Build-Phase-Cohort-3/P-067`.

Nguyễn Minh Đạt (merger backup, chủ repo `Dyo31122005`) uỷ quyền cho AI bấm merge thay mình, với điều kiện:
- Có yêu cầu merge rõ ràng của Nguyễn Minh Đạt trong phiên làm việc, cho đúng các PR được nêu. Uỷ quyền này không phải lời cho phép chung cho mọi PR sau này.
- AI đã review PR. Lỗi nghiêm trọng (bảo mật, mất dữ liệu, phá contract) phải được báo trước khi merge.
- CI pass. Nếu CI đỏ vì lỗi có sẵn từ trước, AI phải nêu rõ là lỗi nào và người yêu cầu phải chấp nhận.
- Dùng merge commit, không squash. PR xếp chồng phải merge đúng thứ tự. Sau mỗi lần merge, kiểm tra bằng `git merge-base --is-ancestor <head> main`.
- Không bao giờ dùng `--admin` để vượt branch protection, và không force-push vào `main`.
- Repo này chỉ có 1 người duy trì nên mọi PR đều do tài khoản `Dyo31122005` mở. Luật "không tự merge PR của chính mình" ở trên được thay bằng: AI review thay người review thứ hai, và mọi lỗi nghiêm trọng phải ghi lại trong PR.

---
**Lưu ý cho AI:** Khi tạo PR, luôn gắn đúng reviewer bắt buộc theo domain ở mục 2. Ngoài ngoại lệ ở trên, AI không tự merge PR trong bất kỳ trường hợp nào — merge luôn do merger chính/backup (con người) quyết định, theo đúng `AGENTS.md` §8.
