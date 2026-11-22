"""Natural-tone v1: friendlier, more flexible Capy without loosening the core contract.

Locks in:
- social turns (greetings, thanks, acknowledgements) route to GENERAL_CONVERSATION,
  but only after every safety branch and never when medication content is present;
- flexible general answers keep the model's reply for low-risk general questions,
  while drug-fact questions and strict mode still get the honest decline;
- a social turn never produces a TOPIC_SWITCH that would wipe conversation state;
- earlier turns reach the model oldest-first with speaker labels, without
  repeating the current message, and recency (not role) decides what fits;
- every patient-facing model turn carries the Vietnamese persona instructions;
- synthesis evidence shows Vietnam local time and Vietnamese dose statuses.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.agents.v2.context import ContextBudget, ContextManager, MemoryKind
from backend.agents.v2.handoff import AgentHandoffResult, DoctorHandoffGateway
from backend.agents.v2.model_gateway import (
    ModelPlan,
    ModelSynthesis,
    OpenAIModelGateway,
    SynthesisEvidence,
    build_model_workloads,
)
from backend.agents.v2.orchestrator import (
    AgentOrchestrator,
    OrchestrationIntent,
    OrchestrationRequest,
    classify_intent,
)
from backend.agents.v2.runtime import AgentRunLimits, ReadOnlyAgentRuntime, RunStatus
from backend.agents.v2.safety import SafetyGateway
from backend.agents.v2.short_term_memory import MessageRole, SessionMemoryKey, ShortTermMemoryStore
from backend.agents.v2.tools import AuthorizedToolContext, ToolGateway

NOW = datetime(2026, 11, 14, 3, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "chào Capy",
        "alo",
        "vâng ạ",
        "ok cảm ơn nhé",
        "cảm ơn bạn nhiều lắm, hôm nay mình thấy đỡ hơn rồi",
        "bạn có khỏe không",
        "hihi",
    ],
)
def test_social_turns_route_to_general_conversation(message):
    assert classify_intent(message, now=NOW).intent is OrchestrationIntent.GENERAL_CONVERSATION


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        # Safety is checked first and always wins over politeness.
        ("cảm ơn, nhưng tôi không muốn sống nữa", OrchestrationIntent.ACUTE_DANGER_ESCALATION),
        ("dạ tôi tăng liều được không", OrchestrationIntent.DOCTOR_REVIEW),
        # Medication/schedule content means it is not small talk.
        ("cảm ơn, hôm nay tôi uống thuốc gì", OrchestrationIntent.TODAY_DOSES),
    ],
)
def test_social_markers_never_mask_safety_or_medication_content(message, expected):
    assert classify_intent(message, now=NOW).intent is expected


# ---------------------------------------------------------------------------
# Orchestrator fixtures
# ---------------------------------------------------------------------------


class _Gateway:
    def __init__(self, reply: str, tool_calls=()):
        self.reply = reply
        self.tool_calls = tool_calls
        self.plan_messages: list[str] = []

    def plan_read_only(self, *, message, actor_role):
        self.plan_messages.append(message)
        return ModelPlan(tool_calls=self.tool_calls, response=self.reply)

    def synthesize_read_only(self, *, message, actor_role, evidence, policy=None, fact_slots=None):
        return ModelSynthesis(free_prose=self.reply)


class _NoTools:
    def __getattr__(self, name):  # any tool call would be a test bug here
        raise AssertionError(f"unexpected tool call: {name}")


class _SafetyDomain:
    def assess(self, *, occurrence_id, evaluated_at):
        raise AssertionError("safety domain must not be reached")


class _HandoffDomain:
    def __init__(self):
        self.created = []

    def create(self, command, *, created_at):
        self.created.append(command.reason_code)
        return AgentHandoffResult(request_id="h-1", status="PENDING", assigned_doctor_id=None, created=True)


def _context_manager(short_term_fraction=0.4):
    return ContextManager(
        ContextBudget(
            input_token_budget=4000,
            output_token_reserve=500,
            total_run_token_budget=5000,
            memory_fractions={
                MemoryKind.SHORT_TERM: short_term_fraction,
                MemoryKind.LONG_TERM_FACT: 0.1,
                MemoryKind.EPISODIC: 0.1,
                MemoryKind.SEMANTIC: 0.1,
            },
        )
    )


def _orchestrator(gateway, *, strict, memory=None, handoffs=None):
    context_manager = _context_manager()
    return AgentOrchestrator(
        runtime=ReadOnlyAgentRuntime(
            gateway,
            limits=AgentRunLimits(
                token_budget=8000, max_steps=6, max_model_calls=2, max_tool_calls=4,
                max_retries=0, model_timeout_seconds=10.0, run_timeout_seconds=20.0,
            ),
        ),
        context_manager=context_manager,
        safety_gateway=SafetyGateway(_SafetyDomain(), timeout_seconds=5.0),
        handoff_gateway=DoctorHandoffGateway(handoffs or _HandoffDomain()),
        short_term_memory=memory,
        now=lambda: NOW,
        strict_general_grounding=strict,
    )


def _request(message, **overrides):
    values = dict(
        message=message, actor_id="actor-1", actor_role="patient", patient_id="patient-1",
        conversation_id="conv-1", session_id="conv-1",
    )
    values.update(overrides)
    return OrchestrationRequest(**values)


def _tools():
    return ToolGateway(_NoTools(), context=AuthorizedToolContext("actor-1", "patient", "patient-1"))


# ---------------------------------------------------------------------------
# Flexible general answers
# ---------------------------------------------------------------------------

_FRIENDLY = "Một vài mẹo nhỏ: gắn giờ uống thuốc với bữa sáng, để thuốc ở chỗ dễ thấy và bật nhắc trong ứng dụng nhé."


def test_flexible_mode_keeps_the_models_answer_for_a_low_risk_general_question():
    orchestrator = _orchestrator(_Gateway(_FRIENDLY), strict=False)

    result = orchestrator.run(_request("làm sao để nhớ uống thuốc đúng giờ"), tools=_tools())

    assert result.intent is OrchestrationIntent.UNKNOWN_OR_AMBIGUOUS
    assert result.status is RunStatus.COMPLETED
    assert result.error_code is None
    assert result.response == _FRIENDLY


def test_flexible_mode_still_declines_an_ungrounded_drug_fact_question():
    orchestrator = _orchestrator(_Gateway("Bạn uống 2 viên mỗi lần là được."), strict=False)

    result = orchestrator.run(_request("Panadol uống mấy viên một ngày"), tools=_tools())

    assert result.error_code == "GROUNDING_FAILURE"
    assert "2 viên" not in result.response


def test_strict_mode_keeps_the_previous_decline_for_general_questions():
    orchestrator = _orchestrator(_Gateway(_FRIENDLY), strict=True)

    result = orchestrator.run(_request("làm sao để nhớ uống thuốc đúng giờ"), tools=_tools())

    assert result.error_code == "GROUNDING_FAILURE"
    assert result.response != _FRIENDLY


def test_flexible_mode_never_relaxes_drug_information_grounding():
    orchestrator = _orchestrator(_Gateway("Metformin trị tiểu đường."), strict=False)

    result = orchestrator.run(_request("Metformin là thuốc gì"), tools=_tools())

    assert result.intent is OrchestrationIntent.DRUG_INFORMATION
    assert "trị tiểu đường" not in result.response


def test_social_turn_gets_a_model_reply_and_never_switches_topic():
    handoffs = _HandoffDomain()
    orchestrator = _orchestrator(_Gateway("Chào bạn, mình là Capy đây!"), strict=False, handoffs=handoffs)

    result = orchestrator.run(
        _request("vâng ạ", prior_active_entity_id="drug-1", prior_active_entity_name="Metformin"), tools=_tools()
    )

    assert result.intent is OrchestrationIntent.GENERAL_CONVERSATION
    assert result.response == "Chào bạn, mình là Capy đây!"
    assert result.follow_up_decision is None  # no TOPIC_SWITCH -> state is kept
    assert handoffs.created == []


# ---------------------------------------------------------------------------
# Conversation memory
# ---------------------------------------------------------------------------


def test_earlier_turns_reach_the_model_oldest_first_with_speakers_and_without_the_current_message():
    memory = ShortTermMemoryStore(_context_manager())
    gateway = _Gateway("Dạ được.")
    orchestrator = _orchestrator(gateway, strict=False, memory=memory)

    orchestrator.run(_request("chào Capy"), tools=_tools())
    orchestrator.run(_request("cảm ơn nhé"), tools=_tools())

    prompt = gateway.plan_messages[-1]
    memory_block = prompt.split("conversation memory", 1)[1]
    assert "Người dùng: chào Capy" in memory_block
    assert "Capy: Dạ được." in memory_block
    assert memory_block.index("Người dùng: chào Capy") < memory_block.index("Capy: Dạ được.")
    assert "cảm ơn nhé" not in memory_block  # the current message is the request, not memory


def test_recency_not_role_decides_which_turns_survive_the_memory_budget():
    tight = _context_manager(short_term_fraction=0.02)  # 80-token memory cap
    memory = ShortTermMemoryStore(tight)
    key = SessionMemoryKey("actor-1", "conv-1", "conv-1")
    start = datetime(2026, 11, 14, 1, 0, tzinfo=UTC)
    memory.append_message(key, entry_id="old-assistant", role=MessageRole.ASSISTANT,
                          content="trả lời dài", token_count=70, created_at=start)
    memory.append_message(key, entry_id="new-user", role=MessageRole.USER,
                          content="câu hỏi mới nhất", token_count=40, created_at=start + timedelta(minutes=1))

    kept = {selection.item.id for selection in tight.build(memory.context_items(key)).included}

    assert "short-term:new-user" in kept
    assert "short-term:old-assistant" not in kept


# ---------------------------------------------------------------------------
# Gateway: persona instructions + localized evidence
# ---------------------------------------------------------------------------


def _settings():
    return SimpleNamespace(
        openai_api_key="test-key", openai_router_api_key="", openai_main_api_key="", openai_fallback_api_key="",
        openai_embedding_api_key="", openai_judge_api_key="", openai_renderer_api_key="",
        agent_router_model="r", agent_main_model="m", agent_fallback_model="f",
        agent_embedding_model="e", rag_judge_model="j", agent_renderer_model="rr",
    )


class _Recorder:
    def __init__(self):
        self.calls = []
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return {"output": [], "output_text": "Dạ.", "usage": {"input_tokens": 1, "output_tokens": 1}}


def test_planner_and_synthesis_both_carry_the_vietnamese_persona_instructions():
    client = _Recorder()
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kw: client)

    gateway.plan_read_only(message="chào Capy", actor_role="patient")
    gateway.synthesize_read_only(message="x", actor_role="patient", evidence=())

    for call in client.calls:
        assert "Bạn là Capy" in call["instructions"]
        assert 'xưng "mình", gọi "bạn"' in call["instructions"]
        assert "115" in call["instructions"]
        assert '"ban"' not in call["input"] and '"minh"' not in call["input"]


def test_synthesis_evidence_uses_vietnam_time_and_vietnamese_statuses_without_mutating_tool_data():
    client = _Recorder()
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kw: client)
    data = {"items": [{"scheduled_at": "2026-11-14T01:00:00+00:00", "status": "TAKEN"}]}

    gateway.synthesize_read_only(
        message="x", actor_role="patient",
        evidence=(SynthesisEvidence(tool_name="get_today_doses", provenance="operational-db", data=data),),
    )

    prompt = client.calls[0]["input"]
    assert "08:00 ngày 14/11/2026 (giờ Việt Nam)" in prompt
    assert "đã uống" in prompt
    assert "TAKEN" not in prompt and "01:00:00+00:00" not in prompt
    assert data["items"][0] == {"scheduled_at": "2026-11-14T01:00:00+00:00", "status": "TAKEN"}
