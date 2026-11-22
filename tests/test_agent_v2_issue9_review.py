"""Regression tests for issue #9 (review of feature/chatbot-natural-tone-v2).

Every routing case below is checked with the semantic classifier OFF: the
keyword router is the last line of defence when the classifier is disabled,
times out or fails, so it must never be weaker than main.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from backend.agents.v2.drug_evidence import WebAnswerCache
from backend.agents.v2.evaluation_v2 import EvaluationPath
from backend.agents.v2.judge_input import build_judge_input
from backend.agents.v2.model_gateway import ModelUsage, WebAnswer
from backend.agents.v2.orchestrator import OrchestrationIntent, _build_schedule_reply, classify_intent
from backend.agents.v2.runtime import ReadOnlyAgentRuntime, RunStatus
from backend.agents.v2.safety_messages import DangerKind, escalation_message
from backend.agents.v2.time_query_engine import TimeGranularity, TimeRange, TimeRelation
from backend.agents.v2.tools import ToolResult
from tests.test_agent_v2_drug_evidence import _CatalogTools, _search_plan, _tools, _WebGateway
from tests.test_agent_v2_orchestrator import _limits

ACUTE = OrchestrationIntent.ACUTE_DANGER_ESCALATION


@pytest.fixture(autouse=True)
def _b3_default_off(monkeypatch):
    from backend.config import get_settings

    monkeypatch.delenv("AGENT_SAFETY_B3_ENABLED", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# -- blocker 1: "đói"/"đời" both fold to "doi" ------------------------------------


@pytest.mark.parametrize(
    "message",
    ["chan doi muon chet", "chán đời muốn chết", "chan doi qua muon chet", "doi muon chet", "ban muon chet a"],
)
def test_unaccented_collisions_never_blank_a_self_harm_phrase(message):
    assert classify_intent(message).intent is ACUTE


@pytest.mark.parametrize("message", ["đói muốn chết", "mệt muốn chết", "met muon chet", "hôm nay nóng muốn chết"])
def test_unambiguous_hyperbole_is_still_a_feeling(message):
    assert classify_intent(message).intent is OrchestrationIntent.GENERAL_CONVERSATION


# -- blocker 2: the check-in tier is off until clinically reviewed ------------------


@pytest.mark.parametrize(
    "message",
    ["buồn muốn chết", "buon muon chet", "chán muốn chết", "cô đơn muốn chết", "khổ muốn chết", "đau muốn chết", "nhức muốn chết"],
)
def test_distress_idioms_escalate_like_main_while_b3_is_off(message):
    assert classify_intent(message).intent is ACUTE


# -- blocker 3: a child's ingestion is never an "ordinary dose" ----------------------


@pytest.mark.parametrize(
    "message",
    [
        "bé nhà tôi 2 tuổi vừa uống 2 viên panadol",
        "be nha toi 2 tuoi vua uong 2 vien panadol",
        "con tôi uống nhầm 1 viên paracetamol",
        "cháu tôi nuốt 1 viên thuốc huyết áp",
    ],
)
def test_child_ingestion_escalates_at_any_pill_count(message):
    decision = classify_intent(message)
    assert decision.intent is ACUTE
    assert decision.danger_kind is DangerKind.OVERDOSE


def test_an_adults_ordinary_paracetamol_dose_question_is_still_not_an_emergency():
    assert classify_intent("Paracetamol uống 2 viên một lần được không?").intent is OrchestrationIntent.MEDICATION_DOSE_SAFETY


def test_an_accidental_double_dose_is_a_possible_overdose_not_a_schedule_question():
    assert classify_intent("tôi lỡ uống 2 liều thuốc huyết áp sáng nay").intent is OrchestrationIntent.POSSIBLE_OVERDOSE


# -- blocker 4: the web cache must not cross patients --------------------------------


def test_the_web_cache_never_serves_another_patients_context():
    gateway = _WebGateway(_search_plan("Amlodipine"))
    runtime = ReadOnlyAgentRuntime(
        gateway, limits=_limits(max_steps=6, max_tool_calls=6), web_search_enabled=True, web_answer_cache=WebAnswerCache()
    )
    question = "Amlodipine có dùng được không?"
    runtime.run(message=f"[memory] user: tôi đang mang thai\n{question}", actor_role="patient", tools=_tools(_CatalogTools([], {})), lookup_query=question)
    runtime.run(message=question, actor_role="patient", tools=_tools(_CatalogTools([], {})), lookup_query=question)

    assert len(gateway.web_calls) == 2  # patient B's answer is generated for patient B
    assert "mang thai" not in gateway.web_calls[1]["message"]


# -- blocker 5: unreviewed emergency texts are not shown --------------------------------


def test_emergency_texts_are_mains_until_b3_is_enabled(monkeypatch):
    from backend.config import get_settings

    default = escalation_message("ACUTE_DANGER_DETECTED", DangerKind.SELF_HARM, handoff_created=True)
    assert default is not None and default.startswith("Hệ thống đã ghi nhận đây là tình huống nguy hiểm cấp tính")
    assert "115" in default
    assert escalation_message("POSSIBLE_OVERDOSE_REPORTED", None, handoff_created=False).startswith(
        "Bạn cho biết có thể đã dùng nhiều thuốc hơn dự định"
    )
    assert escalation_message("SOMETHING_ELSE", None, handoff_created=True) is None

    monkeypatch.setenv("AGENT_SAFETY_B3_ENABLED", "true")
    get_settings.cache_clear()
    assert escalation_message("ACUTE_DANGER_DETECTED", DangerKind.SELF_HARM, handoff_created=True) != default


# -- item 6: "ngày nào cũng giống nhau" only when every day really is ----------------


def _range(start: date, end: date) -> TimeRange:
    tz = "Asia/Ho_Chi_Minh"
    return TimeRange(
        start_datetime=datetime(start.year, start.month, start.day, tzinfo=UTC),
        end_datetime=datetime(end.year, end.month, end.day, 23, 59, tzinfo=UTC),
        timezone=tz,
        granularity=TimeGranularity.WEEK,
        relation=TimeRelation.FUTURE,
        is_past=False,
        is_future=True,
        label="tuần tới",
    )


def _dose(day: int) -> dict:
    return {"scheduled_at": f"2026-11-{day:02d}T01:00:00+00:00", "status": "PENDING", "expected_items": [{"ten_thuoc": "Metformin"}]}


def test_a_range_with_days_off_is_listed_per_day_not_as_every_day():
    now = datetime(2026, 11, 14, 3, 0, tzinfo=UTC)
    reply = _build_schedule_reply([_dose(d) for d in (16, 17, 18, 19, 20)], time_range=_range(date(2026, 11, 16), date(2026, 11, 22)), now=now)
    assert "ngày nào cũng giống nhau" not in reply
    every_day = _build_schedule_reply([_dose(d) for d in range(16, 23)], time_range=_range(date(2026, 11, 16), date(2026, 11, 22)), now=now)
    assert "ngày nào cũng giống nhau" in every_day


# -- item 8: leaflet rows reach the Judge before catalog matches ---------------------


def test_leaflet_rows_are_kept_ahead_of_ten_catalog_items():
    catalog = ToolResult(
        name="search_drug",
        data={"items": [{"legacy_drug_id": f"d{i}", "name": f"Amlodipine {i}"} for i in range(10)]},
    )
    leaflet = ToolResult(
        name="get_drug_info",
        data={"legacy_drug_id": "d0", "results": [{"field": f"f{i}", "content": f"dong to huong dan {i}"} for i in range(5)]},
    )
    payload = build_judge_input(
        query="Amlodipine có gây ho không?", response="Có thể.", path=EvaluationPath.RAG, tool_results=(catalog, leaflet)
    )
    leaflet_snippets = [s for s in payload.retrieved_evidence if s.startswith("to huong dan")]
    assert len(leaflet_snippets) == 5
    assert payload.retrieved_evidence[0].startswith("to huong dan")


# -- item 10: the web answer obeys the token budget ----------------------------------


def test_a_web_answer_over_the_token_budget_is_not_delivered():
    gateway = _WebGateway(
        _search_plan("Ibuprofen"),
        web=WebAnswer(text="dài", searched=True, usage=ModelUsage(input_tokens=50_000, output_tokens=100)),
    )
    runtime = ReadOnlyAgentRuntime(gateway, limits=_limits(max_steps=6, max_tool_calls=6, token_budget=4096), web_search_enabled=True)
    result = runtime.run(message="Ibuprofen có hại dạ dày không", actor_role="patient", tools=_tools(_CatalogTools([], {})))
    assert result.status is RunStatus.BUDGET_EXCEEDED


# -- item 11: a social word does not swallow a follow-up -----------------------------


@pytest.mark.parametrize("message", ["ok, thế còn Amlodipine thì sao", "ok thanks, còn metformin thì sao"])
def test_a_follow_up_with_a_social_word_is_not_small_talk(message):
    assert classify_intent(message).intent is not OrchestrationIntent.GENERAL_CONVERSATION


@pytest.mark.parametrize("message", ["cảm ơn Capy nhiều nhé", "chào Capy", "vâng ạ"])
def test_plain_small_talk_is_still_small_talk(message):
    assert classify_intent(message).intent is OrchestrationIntent.GENERAL_CONVERSATION
