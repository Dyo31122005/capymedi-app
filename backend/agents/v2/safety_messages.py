"""B3: patient-facing safety texts for Agent V2, in one place for clinical review.

Two tiers:

* EMERGENCY -- a clear danger (keyword router or semantic classifier). Fixed
  text, a Doctor Handoff is created, the Main Model is never the author.
  One text per danger kind, because "don't take more medicine" is the right
  first instruction for an overdose but the wrong one for someone thinking
  about suicide, and chest pain needs "don't drive yourself", not either.
* CHECK-IN -- an ambiguous distress phrase ("buồn muốn chết", "đau muốn
  chết"). Fixed text that asks directly and names the 115 signs; no handoff
  yet. An affirmative answer on the next turn escalates to EMERGENCY (see
  AgentOrchestrator.run).

STATUS: drafted by engineering on 2026-11-14 and NOT yet clinically
reviewed. Before production, a clinician must review every text here, and
decide whether to add a mental-health hotline number (none is included:
only numbers we can verify belong in a fixed safety text).

Invariants pinned by tests: every EMERGENCY text names 115 and a doctor
("bác sĩ") and never contains a dosing quantity ("viên"/"vien").
"""

from __future__ import annotations

from enum import StrEnum


class DangerKind(StrEnum):
    SELF_HARM = "SELF_HARM"
    OVERDOSE = "OVERDOSE"
    SEVERE_SYMPTOM = "SEVERE_SYMPTOM"
    OTHER = "OTHER"


class CheckInKind(StrEnum):
    EMOTIONAL = "EMOTIONAL"
    PAIN = "PAIN"


# -- EMERGENCY: handoff created ------------------------------------------------

_ACUTE_CREATED: dict[DangerKind, str] = {
    DangerKind.SELF_HARM: (
        "Cảm ơn bạn đã nói cho mình biết. Nghe vậy mình rất lo cho bạn, và bạn không phải chịu "
        "đựng chuyện này một mình đâu. Mình đã báo để bác sĩ liên hệ với bạn sớm nhất.\n\n"
        "Nếu ngay lúc này bạn đang nghĩ đến việc làm hại bản thân, hãy gọi 115 hoặc nhờ người "
        "thân đưa đến cơ sở y tế gần nhất ngay. Bạn hãy ở cạnh một người mình tin tưởng, và để "
        "thuốc men, vật sắc nhọn ra xa mình nhé."
    ),
    DangerKind.OVERDOSE: (
        "Đây có thể là tình huống nguy hiểm, bạn hãy gọi 115 ngay hoặc đến cơ sở y tế gần nhất, "
        "nhớ mang theo vỏ hộp hoặc vỉ thuốc đã uống. Đừng tự gây nôn và đừng uống thêm thuốc gì "
        "để \"giải\". Nếu được, hãy nhờ một người ở bên cạnh.\n\n"
        "Mình đã báo bác sĩ để hỗ trợ bạn sớm nhất, nhưng đừng chờ phản hồi mới đi cấp cứu nhé."
    ),
    DangerKind.SEVERE_SYMPTOM: (
        "Những dấu hiệu bạn kể có thể là tình trạng cấp cứu. Bạn hãy gọi 115 ngay hoặc nhờ người "
        "đưa đến cơ sở y tế gần nhất, đừng tự lái xe. Trong lúc chờ, hãy ngồi hoặc nằm nghỉ ở tư "
        "thế dễ thở và không tự uống thêm thuốc khi chưa có chỉ dẫn.\n\n"
        "Mình đã báo bác sĩ để hỗ trợ bạn, nhưng đừng chờ phản hồi mới đi cấp cứu nhé."
    ),
    DangerKind.OTHER: (
        "Mình lo cho sự an toàn của bạn nên đã báo bác sĩ để được ưu tiên xem xét. Nếu đây là "
        "tình huống khẩn cấp ngay bây giờ, hãy gọi 115 hoặc đến cơ sở y tế gần nhất, đừng chờ "
        "phản hồi. Không tự ý uống thêm thuốc, và nếu có thể, hãy ở cạnh một người thân."
    ),
}

# -- EMERGENCY: handoff could NOT be created ----------------------------------
# Never claims a doctor was notified; the emergency instruction comes first.

_ACUTE_NOT_CREATED: dict[DangerKind, str] = {
    DangerKind.SELF_HARM: (
        "Nghe bạn nói vậy mình rất lo cho bạn. Nếu ngay lúc này bạn đang nghĩ đến việc làm hại "
        "bản thân, hãy gọi 115 hoặc nhờ người thân đưa đến cơ sở y tế gần nhất ngay, và ở cạnh "
        "một người bạn tin tưởng. Mình chưa kết nối được với bác sĩ lúc này, mình sẽ thử lại, "
        "nhưng bạn đừng chờ nhé."
    ),
    DangerKind.OVERDOSE: (
        "Đây có thể là tình huống nguy hiểm, bạn hãy gọi 115 ngay hoặc đến cơ sở y tế gần nhất, "
        "mang theo vỏ hộp hoặc vỉ thuốc đã uống. Đừng tự gây nôn và đừng uống thêm thuốc gì. "
        "Mình chưa kết nối được với bác sĩ lúc này, bạn đừng chờ nhé."
    ),
    DangerKind.SEVERE_SYMPTOM: (
        "Những dấu hiệu bạn kể có thể là tình trạng cấp cứu. Bạn hãy gọi 115 ngay hoặc nhờ người "
        "đưa đến cơ sở y tế gần nhất, đừng tự lái xe. Mình chưa kết nối được với bác sĩ lúc này, "
        "bạn đừng chờ nhé."
    ),
    DangerKind.OTHER: (
        "Nếu đây là tình huống khẩn cấp, hãy gọi 115 hoặc đến cơ sở y tế gần nhất ngay. Mình chưa "
        "kết nối được với bác sĩ lúc này, bạn đừng chờ nhé."
    ),
}

# -- POSSIBLE OVERDOSE (accidental extra / double dose) -----------------------

_POSSIBLE_OVERDOSE_CREATED = (
    "Mình đã báo bác sĩ xem giúp trường hợp uống dư thuốc này. Trong lúc chờ, đừng tự uống thêm "
    "thuốc gì để \"bù\" hay \"giải\", còn liều kế tiếp thì đợi bác sĩ hướng dẫn nhé.\n\n"
    "Nếu thấy chóng mặt nhiều, mệt lả, tim đập bất thường, khó thở hay ngất, hãy gọi 115 hoặc "
    "liên hệ Trung tâm Chống độc ngay. Nếu được, bạn ghi lại tên thuốc, lượng đã uống và giờ uống "
    "để bác sĩ hỗ trợ nhanh hơn."
)
_POSSIBLE_OVERDOSE_NOT_CREATED = (
    "Mình chưa kết nối được với bác sĩ lúc này. Đừng tự uống thêm thuốc gì để xử lý; nếu thấy "
    "chóng mặt nhiều, mệt lả, tim đập bất thường, khó thở hay ngất, hãy gọi 115 hoặc liên hệ cơ "
    "sở y tế, Trung tâm Chống độc ngay."
)

# -- CHECK-IN -------------------------------------------------------------------

CHECK_IN_MESSAGES: dict[CheckInKind, str] = {
    CheckInKind.EMOTIONAL: (
        "Nghe bạn nói vậy mình thương lắm. Mình muốn hỏi thật lòng một câu: có lúc nào bạn nghĩ "
        "đến chuyện không muốn sống nữa, hay muốn làm hại bản thân không? Bạn cứ nói thật với mình "
        "nhé, mình ở đây lắng nghe.\n\n"
        "Nếu ý nghĩ đó đang mạnh lên ngay lúc này, bạn hãy gọi 115 hoặc gọi ngay cho một người "
        "thân tin cậy."
    ),
    CheckInKind.PAIN: (
        "Bạn đang đau nhiều quá, mình lo cho bạn. Bạn đau ở đâu, và có kèm khó thở, đau thắt ngực, "
        "vã mồ hôi, ngất xỉu, hay yếu, tê một bên người không?\n\n"
        "Nếu có bất kỳ dấu hiệu nào như vậy, hoặc cơn đau dữ dội và đột ngột, hãy gọi 115 ngay nhé."
    ),
}
# The escalation that an affirmative answer to each check-in maps to.
CHECK_IN_CONFIRMED_DANGER: dict[CheckInKind, DangerKind] = {
    CheckInKind.EMOTIONAL: DangerKind.SELF_HARM,
    CheckInKind.PAIN: DangerKind.SEVERE_SYMPTOM,
}


def acute_danger_message(kind: DangerKind | None, *, handoff_created: bool) -> str:
    table = _ACUTE_CREATED if handoff_created else _ACUTE_NOT_CREATED
    return table[kind or DangerKind.OTHER]


def possible_overdose_message(*, handoff_created: bool) -> str:
    return _POSSIBLE_OVERDOSE_CREATED if handoff_created else _POSSIBLE_OVERDOSE_NOT_CREATED


# The emergency texts live on main before B3 (backend/agents/v2/runtime.py
# at origin/main), verbatim. Used whenever ``agent_safety_b3_enabled`` is off,
# i.e. until the B3 texts above are clinically reviewed (issue #9, blocker 5).
_MAIN_ESCALATION_TEXTS: dict[tuple[str, bool], str] = {
    ("ACUTE_DANGER_DETECTED", False): (
        "Hệ thống nhận thấy tin nhắn của bạn có dấu hiệu nguy hiểm cấp tính và đang "
        "chuyển ngay đến bác sĩ để được ưu tiên xem xét. NẾU đây là tình huống khẩn "
        "cấp ngay bây giờ, hãy gọi cấp cứu 115 (Việt Nam) hoặc số khẩn cấp tại nơi bạn "
        "đang ở -- đừng chờ phản hồi từ hệ thống này. Không tự ý uống thêm thuốc. Nếu "
        "có thể, hãy ở gần một người bạn tin cậy ngay lúc này."
    ),
    ("ACUTE_DANGER_DETECTED", True): (
        "Hệ thống đã ghi nhận đây là tình huống nguy hiểm cấp tính và đã chuyển đến "
        "bác sĩ để được ưu tiên xem xét. NẾU đây là tình huống khẩn cấp ngay bây giờ, "
        "hãy gọi cấp cứu 115 (Việt Nam) hoặc số khẩn cấp tại nơi bạn đang ở -- đừng chờ "
        "bác sĩ phản hồi. Không tự ý uống thêm thuốc. Nếu có thể, hãy ở gần một người "
        "bạn tin cậy ngay lúc này."
    ),
    ("POSSIBLE_OVERDOSE_REPORTED", False): (
        "Bạn cho biết có thể đã dùng nhiều thuốc hơn dự định. Để bảo đảm an toàn, hệ thống đang "
        "chuyển yêu cầu đến bác sĩ. Hãy liên hệ ngay cơ sở y tế, Trung tâm Chống độc hoặc gọi 115 "
        "(Việt Nam) nếu bạn có bất kỳ triệu chứng bất thường nào; không tự uống thêm thuốc để xử lý."
    ),
    ("POSSIBLE_OVERDOSE_REPORTED", True): (
        "Hệ thống đã chuyển yêu cầu để bác sĩ ưu tiên xem xét vì bạn có thể đã dùng nhiều thuốc "
        "hơn dự định. Hãy liên hệ ngay cơ sở y tế, Trung tâm Chống độc hoặc gọi 115 (Việt Nam) nếu "
        "có triệu chứng bất thường; không tự uống thêm thuốc để xử lý."
    ),
}


def b3_enabled() -> bool:
    """Whether the clinically-unreviewed B3 tier is switched on."""
    from backend.config import get_settings

    return bool(get_settings().agent_safety_b3_enabled)


def escalation_message(reason_code: str | None, danger_kind: DangerKind | None, *, handoff_created: bool) -> str | None:
    """The emergency text for a Safety reason code, or ``None`` when the
    reason code is not an escalation (the caller's generic text applies)."""
    if not b3_enabled():
        return _MAIN_ESCALATION_TEXTS.get((reason_code or "", handoff_created))
    if reason_code == "ACUTE_DANGER_DETECTED":
        return acute_danger_message(danger_kind, handoff_created=handoff_created)
    if reason_code == "POSSIBLE_OVERDOSE_REPORTED":
        return possible_overdose_message(handoff_created=handoff_created)
    return None


def check_in_kind_of_reply(text: str | None) -> CheckInKind | None:
    """Which check-in (if any) an earlier assistant reply was."""
    if not text:
        return None
    for kind, message in CHECK_IN_MESSAGES.items():
        if text.strip() == message.strip():
            return kind
    return None
