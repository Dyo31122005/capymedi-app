"""Config-driven, provider-neutral model boundary for the isolated Agent V2 path.

BUILD-2 keeps this boundary backend-only.  It has no database access and its
only callable functions are the six read-only tools already approved by
BUILD-1.  ``AGENT_RUNTIME_ENABLED`` remains the route-level exposure gate.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import openai

from backend.agents.v2.time_query_engine import DOSE_STATUS_LABELS_VI, PATIENT_TIMEZONE

if TYPE_CHECKING:
    # TASK-V2.5-004: type-only import to avoid a circular dependency --
    # response_policy.py itself imports SynthesisEvidence from this module.
    # policy/fact_slots are optional, backward-compatible additions to
    # synthesize_read_only (see the Protocol/DisabledModelGateway/
    # StaticModelGateway/OpenAIModelGateway below); every existing caller
    # that omits them keeps today's exact behavior unchanged.
    from backend.agents.v2.response_policy import RenderableFactSlots, ResponsePolicy


class ModelRole(StrEnum):
    ROUTER = "router"
    MAIN = "main"
    FALLBACK = "fallback"
    EMBEDDING = "embedding"
    JUDGE = "judge"
    # TASK-V2.5-004 (CP0 ADR delta 1.3a/1.4a): a separate workload for the
    # natural-language renderer, deliberately distinct from MAIN even though
    # both call ``synthesize_read_only``-shaped turns. Sharing MAIN would
    # mean changing the renderer's model (e.g. for cost/latency reasons)
    # silently also changes the planner's model -- the exact coupling bug
    # this role exists to avoid.
    RENDERER = "renderer"


@dataclass(frozen=True)
class ModelWorkload:
    role: ModelRole
    model: str
    api_key: str
    credential_source: str
    preferred_credential_env: str
    # Optional Responses API reasoning effort for this workload. ``None`` sends
    # no ``reasoning`` parameter at all (the model's own default applies), so
    # every workload built without it behaves exactly as before.
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class ModelSmokeResult:
    role: ModelRole
    model: str
    passed: bool
    latency_ms: float
    usage: ModelUsage
    request_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class EmbeddingResult:
    """Typed vector result for Agent V2 retrieval; never includes credentials."""

    model: str
    vector: tuple[float, ...]
    usage: ModelUsage = ModelUsage()
    request_id: str | None = None


class MissingModelCredentialError(RuntimeError):
    """Raised before a request when an explicitly named backend env var is absent."""


class EmptySynthesisError(ValueError):
    """BUILD-32: raised in place of a bare ``ValueError`` so the runtime's
    retry/failure classification (``backend.agents.v2.runtime``) can attach
    the canonical ``EMPTY_REPLY`` error code precisely, instead of folding
    this into the generic ``MODEL_ERROR`` bucket. Still a ``ValueError``
    subclass so any existing ``except ValueError`` handling keeps working
    unchanged."""


class ProhibitedClaimLeakError(ValueError):
    """TASK-V2.5-004: raised when ``response_policy.validate_free_prose``
    finds the renderer's own ``free_prose`` output contains a claim from a
    category ``ResponsePolicy.prohibited_claim_categories`` disallows (dose
    time/status, medication identity, handoff state) -- a model that
    hallucinated a sensitive claim on its own, from nothing (it was never
    shown the fact value; see ``RendererContext``). Deliberately a sibling
    of ``EmptySynthesisError``, not a subclass of it -- this is not an empty
    reply, it is an unauthorized one, and the runtime classifies it under
    its own error code so Admin Monitoring can tell the two apart. Fails
    closed through the exact same bounded-retry-then-FAILED path; the
    backend's ``assemble_reply`` is never called with this attempt's output."""


def _setting(settings: Any, name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def build_model_workloads(settings: Any) -> dict[ModelRole, ModelWorkload]:
    """Resolve workload models and credential references without logging secrets.

    A workload-specific key wins.  The pre-existing backend-only
    ``OPENAI_API_KEY`` is an intentional local-development fallback from the
    approved plan, not a client-side configuration mechanism.
    """

    global_key = _setting(settings, "openai_api_key")
    definitions = (
        (ModelRole.ROUTER, "agent_router_model", "openai_router_api_key", "OPENAI_ROUTER_API_KEY"),
        (ModelRole.MAIN, "agent_main_model", "openai_main_api_key", "OPENAI_MAIN_API_KEY"),
        (ModelRole.FALLBACK, "agent_fallback_model", "openai_fallback_api_key", "OPENAI_FALLBACK_API_KEY"),
        (ModelRole.EMBEDDING, "agent_embedding_model", "openai_embedding_api_key", "OPENAI_EMBEDDING_API_KEY"),
        (ModelRole.JUDGE, "rag_judge_model", "openai_judge_api_key", "OPENAI_JUDGE_API_KEY"),
        (ModelRole.RENDERER, "agent_renderer_model", "openai_renderer_api_key", "OPENAI_RENDERER_API_KEY"),
    )
    # Only the MAIN workload (planner + synthesis) is configurable today; an
    # empty/absent setting means "send no reasoning parameter".
    reasoning_efforts = {ModelRole.MAIN: _setting(settings, "agent_main_reasoning_effort") or None}
    workloads: dict[ModelRole, ModelWorkload] = {}
    for role, model_setting, key_setting, preferred_env in definitions:
        workload_key = _setting(settings, key_setting)
        workloads[role] = ModelWorkload(
            role=role,
            model=_setting(settings, model_setting),
            api_key=workload_key or global_key,
            credential_source=preferred_env if workload_key else "OPENAI_API_KEY",
            preferred_credential_env=preferred_env,
            reasoning_effort=reasoning_efforts.get(role),
        )
    return workloads


def missing_model_credentials(workloads: dict[ModelRole, ModelWorkload]) -> tuple[str, ...]:
    """Return only env-var names; values are intentionally never returned."""

    return tuple(workload.preferred_credential_env for workload in workloads.values() if not workload.api_key)


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _usage(response: Any) -> ModelUsage:
    usage = _value(response, "usage")
    details = _value(usage, "input_tokens_details", {})
    return ModelUsage(
        input_tokens=_value(usage, "input_tokens") or _value(usage, "prompt_tokens"),
        cached_input_tokens=_value(details, "cached_tokens"),
        output_tokens=_value(usage, "output_tokens"),
    )


@lru_cache(maxsize=16)
def _shared_openai_client(api_key: str, timeout: float) -> Any:
    return openai.OpenAI(api_key=api_key, max_retries=0, timeout=timeout)


def openai_client(api_key: str, *, timeout: float, factory: Callable[..., Any] = openai.OpenAI) -> Any:
    """SDK retries are disabled so the runtime owns the exact retry/model call
    budget; the SDK-level timeout bounds each outbound request.

    The real client is built once per (key, timeout) and shared process-wide:
    building one costs ~130 ms (TLS context) plus a fresh connection, and the
    SDK client is thread-safe. Injected factories (tests) are called as-is."""
    if factory is openai.OpenAI:
        return _shared_openai_client(api_key, timeout)
    return factory(api_key=api_key, max_retries=0, timeout=timeout)


def reasoning_kwargs(effort: str | None) -> dict[str, Any]:
    """``{"reasoning": {"effort": ...}}`` when an effort is configured,
    otherwise nothing -- spread into ``responses.create`` so an unconfigured
    workload sends byte-identical requests to before."""
    return {"reasoning": {"effort": effort}} if effort else {}


def _request_id(response: Any) -> str | None:
    request_id = _value(response, "_request_id") or _value(response, "request_id")
    return str(request_id) if request_id else None


def _safe_error(error: Exception) -> str:
    """Keep smoke telemetry useful without leaking messages, prompts, or keys."""

    status = getattr(error, "status_code", None)
    return f"{type(error).__name__}{f' (HTTP {status})' if status else ''}"


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict


@dataclass(frozen=True)
class ModelPlan:
    tool_calls: tuple[ToolCall, ...] = ()
    response: str = ""
    usage: ModelUsage = ModelUsage()
    request_id: str | None = None


@dataclass(frozen=True)
class SynthesisEvidence:
    """One already-executed, already-verified tool result for the synthesis turn.

    Deliberately independent of ``backend.agents.v2.tools.ToolResult`` so this
    module keeps its existing zero-dependency-on-tools.py layering; the
    runtime converts a ``ToolResult`` into this shape before calling
    ``synthesize_read_only``.
    """

    tool_name: str
    provenance: str
    data: dict


@dataclass(frozen=True)
class ModelSynthesis:
    """TASK-V2.5-004: renamed from ``response`` to ``free_prose`` (CP1
    contract mục 4a, corrective PR #191) -- this field is no longer
    guaranteed to BE the whole final reply once a caller opts into the
    renderer contract (``policy``/``fact_slots`` below): it is only ever the
    model's own connective/empathy prose. ``backend.agents.v2.response_
    policy.assemble_reply`` is what combines it with any protected fact
    strings into the true final reply text.

    When a caller does NOT opt in (omits ``policy``/``fact_slots`` from
    ``synthesize_read_only``, the unchanged default), ``free_prose`` is
    exactly what ``response`` used to mean: the model's full final reply,
    produced from the full unrestricted evidence exactly as before this
    task -- ``assemble_reply`` against empty fact slots is then a pure
    passthrough, so this rename carries no behavior change for that path.
    """

    free_prose: str = ""
    usage: ModelUsage = ModelUsage()
    request_id: str | None = None


@dataclass(frozen=True)
class WebAnswer:
    """C2/E1 (MVP): the Main Model's reply grounded on its hosted web search,
    used when internal data had nothing (see
    ``ReadOnlyAgentRuntime._answer_from_web``). ``searched`` is False when the
    model answered without actually running a search -- such a reply is not
    web-grounded and the runtime discards it."""

    text: str
    citations: tuple[dict[str, str], ...] = ()
    searched: bool = False
    usage: ModelUsage = ModelUsage()
    request_id: str | None = None


class ModelGateway(Protocol):
    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan: ...

    def synthesize_read_only(
        self,
        *,
        message: str,
        actor_role: str,
        evidence: tuple[SynthesisEvidence, ...],
        # TASK-V2.5-004: optional, additive opt-in (CP1 contract mục 4a).
        # `None` (the default every existing caller uses) preserves today's
        # exact MAIN-workload, full-evidence behavior byte-for-byte -- see
        # OpenAIModelGateway.synthesize_read_only's own docstring for the
        # precise branch this selects. Only a caller that has already built
        # a real ResponsePolicy/RenderableFactSlots (i.e. the
        # AGENT_V2_5_RENDERER_ENABLED-gated path in runtime.py) passes these.
        policy: ResponsePolicy | None = None,
        fact_slots: RenderableFactSlots | None = None,
    ) -> ModelSynthesis: ...


class EmbeddingGateway(Protocol):
    def embed_query(self, *, text: str) -> EmbeddingResult: ...


class DisabledModelGateway:
    """Safe production default until BUILD-2 model smoke tests are approved."""

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        return ModelPlan(response="Agent V2 dang chua duoc kich hoat de tra loi.")

    def synthesize_read_only(
        self,
        *,
        message: str,
        actor_role: str,
        evidence: tuple[SynthesisEvidence, ...],
        policy: ResponsePolicy | None = None,
        fact_slots: RenderableFactSlots | None = None,
    ) -> ModelSynthesis:
        return ModelSynthesis(free_prose="Agent V2 dang chua duoc kich hoat de tra loi.")


class StaticModelGateway:
    """Deterministic test double; it never calls an external model."""

    def __init__(self, plan: ModelPlan, synthesis: ModelSynthesis | None = None) -> None:
        self.plan = plan
        # Deliberately not derived from ``plan.response``: defaulting a
        # tool-calling synthesis reply to the pre-tool planning text is
        # exactly the BUILD-19 defect this double must not reintroduce by
        # accident. Tests that care about the synthesized text pass it.
        self.synthesis = synthesis if synthesis is not None else ModelSynthesis(free_prose="synthesized-reply")

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        return self.plan

    def synthesize_read_only(
        self,
        *,
        message: str,
        actor_role: str,
        evidence: tuple[SynthesisEvidence, ...],
        policy: ResponsePolicy | None = None,
        fact_slots: RenderableFactSlots | None = None,
    ) -> ModelSynthesis:
        return self.synthesis


_ROUTER_SCHEMA = {
    "type": "object",
    "properties": {"intent": {"type": "string"}},
    "required": ["intent"],
    "additionalProperties": False,
}

_READ_ONLY_TOOL_SCHEMAS = (
    {
        "type": "function",
        "name": "search_drug",
        "description": "Search the canonical drug catalog by a short query.",
        "strict": True,
        "parameters": {
            "type": "object",
            # BUILD-46 (Fix A, found live during BUILD-45's own production
            # validation): these bounds MUST mirror
            # backend.agents.v2.tools.SearchDrugArguments exactly (the
            # required invariant: model-visible schema constraints ==
            # runtime validation constraints). Before this fix, the schema
            # declared only bare "type" with no bound at all, so a model
            # that picked limit=0 or limit=50 (or an empty query) passed
            # schema-shape validation but then failed
            # ToolGateway.execute()'s own Pydantic input_model.model_validate
            # with INVALID_TOOL_ARGUMENTS, hard-failing the whole turn --
            # reproduced live on production. Note (researched, not assumed):
            # OpenAI's own structured-outputs/strict-mode documentation
            # states minLength/maxLength/minimum/maximum are NOT enforced by
            # constrained decoding the way type/enum/required are -- this is
            # harm reduction (the model sees and typically respects the
            # declared bound; a real API call with these keys present was
            # verified to still be accepted, not rejected), not an absolute
            # guarantee. The Pydantic runtime validation below remains the
            # actual fail-closed safety net for any residual case.
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 100},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_drug_info",
        "description": "Read approved canonical details for one resolved legacy drug id.",
        "strict": True,
        "parameters": {
            "type": "object",
            # BUILD-46: same class of gap found+fixed for search_drug above,
            # audited into this tool too (backend.agents.v2.tools.
            # GetDrugInfoArguments) -- not observed live, but the same
            # unstated-bound shape, closed for full contract consistency.
            "properties": {
                "legacy_drug_id": {"type": "string", "minLength": 1, "maxLength": 200},
                "query": {"type": "string", "maxLength": 500},
            },
            "required": ["legacy_drug_id", "query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_active_prescriptions",
        "description": "Read the authorized patient's active prescriptions.",
        "strict": True,
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "get_today_doses",
        "description": "Read the authorized patient's doses scheduled today.",
        "strict": True,
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "get_upcoming_doses",
        "description": "Read the authorized patient's upcoming doses.",
        "strict": True,
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "get_dose_status",
        "description": "Read the status of one authorized dose group.",
        "strict": True,
        "parameters": {
            "type": "object",
            # BUILD-46: same class of gap as search_drug above, audited into
            # this tool too (backend.agents.v2.tools.GetDoseStatusArguments).
            "properties": {"dose_id": {"type": "string", "minLength": 1, "maxLength": 200}},
            "required": ["dose_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_doses_for_range",
        # BUILD-27B: no date/range parameters here on purpose -- the server
        # (not the model) has already resolved the exact date or range this
        # specific request means (e.g. "hôm qua", "ngày kia", "20/08") from
        # the message before this tool is ever offered; calling it always
        # reads that pre-resolved range. Use this instead of
        # get_today_doses/get_upcoming_doses whenever the request names a
        # specific past date, a specific future date beyond tomorrow, or a
        # week ("tuần trước"/"tuần tới") -- those two tools only ever cover
        # exactly today or a short rolling forward window.
        "description": (
            "Read the authorized patient's doses for the specific past or future "
            "date/date-range the server has already resolved for this request. "
            "Takes no arguments -- the range is fixed server-side, not chosen here."
        ),
        "strict": True,
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
)


# Patient-facing persona, sent as the system-level ``instructions`` of EVERY
# patient-facing model turn (planner, synthesis, renderer) so the voice is the
# same whether or not a tool was called. Replaces TASK-023's English, ASCII-only
# excerpt, which made the model print "ban"/"minh" without diacritics and was
# absent from the planner turn (whose text IS the reply when no tool is called).
# Tone never outranks the boundaries listed at the end: those restate the
# existing safety/grounding/read-only contract in the patient's language, and
# every per-turn rule in the ``input`` of each call still applies unchanged.
_CAPY_SYSTEM_INSTRUCTIONS = """Bạn là Capy, trợ lý sức khỏe trong ứng dụng nhắc uống thuốc CapyMedi. Người dùng phần lớn là bệnh nhân bệnh mạn tính, nhiều người đã lớn tuổi.

GIỌNG ĐIỆU
- Ấm áp, gần gũi, kiên nhẫn như một người cháu hiểu biết về thuốc và luôn quan tâm; tôn trọng, không giáo điều, không máy móc.
- Mặc định xưng "mình", gọi "bạn". Nếu người dùng tự xưng là ông, bà, bác, cô, chú thì gọi đúng như vậy và xưng "cháu"; nếu tự xưng anh, chị thì xưng "em". Giữ nhất quán suốt cuộc trò chuyện.
- Luôn viết tiếng Việt có dấu đầy đủ, câu ngắn, từ ngữ đời thường. Không dùng thuật ngữ kỹ thuật (tool, hệ thống, dữ liệu canonical, truy xuất, mã trạng thái...); nói "theo lịch thuốc của bạn", "theo thông tin thuốc mình tra được".
- Khi người dùng chia sẻ cảm xúc hay tình trạng (mệt, lo, buồn, vui, cảm ơn, thấy đỡ hơn), đáp lại điều đó trước bằng một câu chân thành rồi mới đến thông tin.
- Trả lời thẳng vào điều được hỏi trước, rồi mới thêm ý thật sự hữu ích. Câu hỏi đơn giản thì trả lời 1–3 câu.
- Chào hỏi, cảm ơn, tán gẫu ngắn: đáp tự nhiên, thân thiện như người thật, có thể gợi ý nhẹ một việc mình giúp được. Không coi đó là câu hỏi y khoa.
- Chỉ hỏi lại khi thật sự thiếu một thông tin quan trọng, mỗi lần một câu hỏi.
- Đổi cách mở đầu cho tự nhiên, không lặp một khuôn; không phải câu nào cũng bắt đầu bằng "Dạ". Hạn chế biểu tượng cảm xúc (tối đa một, và chỉ khi trò chuyện vui vẻ).
- Động viên khi người dùng uống thuốc đều; không trách móc khi quên liều.
- Không tự liệt kê menu kiểu "Bạn có muốn hỏi thêm về..." ở cuối câu trả lời; ứng dụng đã tự hiển thị gợi ý.
- Câu nói cường điệu đời thường ("mệt muốn chết", "nóng muốn chết", "đói muốn chết") là cách nói cho mạnh: hỏi han đúng cảm giác đó (mệt, nóng, đói), không nhắc tới tự tử, 115 hay cấp cứu nếu người dùng không nêu dấu hiệu nguy hiểm nào khác.

CÁCH TRẢ LỜI CHO DỄ HIỂU
- Mặc định người đọc không có kiến thức y khoa. Gặp thuật ngữ bắt buộc phải dùng thì giải thích ngay bằng lời thường (ví dụ "hạ đường huyết, tức là đường trong máu xuống quá thấp"); mỗi câu tối đa một thuật ngữ mới.
- Nếu câu trả lời phụ thuộc điều kiện, nói điều kiện ngay câu đầu; không mở bằng "Có"/"Không" rồi tự sửa ý ở câu sau.
- Nói mức độ đáng lo cho tương xứng bằng lời đời thường (thường gặp và thường nhẹ / ít gặp / hiếm nhưng cần đi khám ngay). Không hứa chắc "không sao đâu", nhưng cũng không kể thêm biến chứng hiếm hay bệnh nặng khi người dùng không nêu dấu hiệu gì gợi ý.
- Khi người dùng hỏi một triệu chứng có liên quan tới thuốc không: nếu thông tin thuốc đã tra được có nhắc tới triệu chứng đó thì nói rõ là có thể liên quan, nói thêm là vẫn có thể do nguyên nhân khác, rồi nêu việc nên làm tương xứng.
- Dùng lời dẫn tự nhiên như "bạn có thể...", "điều nên làm lúc này là..." thay cho tiêu đề máy móc kiểu "Bước tiếp theo:", "Lưu ý:". Câu trả lời ngắn thì viết thành câu liền mạch, không cần gạch đầu dòng hay chữ đậm.
- Không lặp lại lời khuyên hay phần giải thích đã nói ở lượt trước; câu hỏi nối tiếp thì trả lời đúng điểm mới.
- Khi người dùng vừa trả lời câu mình hỏi lại, dùng ngay thông tin đó để trả lời trọn vẹn, không hỏi lại điều đã biết.
- Nếu lời khuyên khác đi vì điều người dùng đã kể trong cuộc trò chuyện, nói ngắn lý do ("vì bạn có nói là...").
- Nhắc hỏi bác sĩ hoặc dược sĩ chỉ khi việc đó thật sự thay đổi điều người dùng nên làm; không dùng nó để thay cho phần mình trả lời được. Không tự thêm câu "thông tin chỉ mang tính tham khảo" vì ứng dụng đã hiển thị sẵn dòng lưu ý đó.

PHẠM VI
- Capy được làm: chào hỏi, trò chuyện thường ngày, lắng nghe và an ủi; chuyện ăn uống, ngủ nghỉ, vận động, sinh hoạt liên quan đến sức khỏe; thuốc và lịch uống thuốc của người dùng; kiến thức sức khỏe phổ thông.
- Ngoài phạm vi: viết hoặc sửa code, làm bài tập, giải toán, viết văn hay soạn văn bản, dịch thuật; giá cả, chứng khoán, tiền ảo, xổ số; tin tức, thời sự, kết quả thể thao, thời tiết; chính trị, tôn giáo, pháp luật; kỹ thuật máy tính và các việc chuyên môn khác không liên quan sức khỏe.
- Với yêu cầu ngoài phạm vi: KHÔNG làm, kể cả làm một phần. Xin lỗi ngắn gọn, nói rõ việc đó nằm ngoài khả năng của Capy, rồi nhắc nhẹ một câu là Capy giúp được chuyện thuốc men, sức khỏe hoặc trò chuyện. Giữ giọng thân thiện, không giảng giải.
- Một câu tán gẫu có nhắc tới chủ đề đó (ví dụ "trời nóng quá", "hôm nay xem bóng đá vui ghê") vẫn là trò chuyện thường ngày: đáp tự nhiên, có thể gắn với sức khỏe (uống đủ nước, nghỉ ngơi), không cần xin lỗi.

RANH GIỚI (luôn giữ, kể cả khi người dùng yêu cầu khác)
- Không chẩn đoán bệnh, không kê đơn, không khuyên tăng, giảm, ngừng hay đổi thuốc hoặc liều. Kể cả khi tờ hướng dẫn ghi "ngừng thuốc" cho một dấu hiệu nặng, chỉ nói gặp dấu hiệu đó thì đi khám hoặc gọi 115 ngay; không nhắc tới chuyện ngừng hay tiếp tục thuốc.
- Thông tin cụ thể về một thuốc (công dụng, liều, cách dùng, tác dụng phụ, chống chỉ định, tương tác) và về lịch hay trạng thái liều của người dùng chỉ được nói khi có trong dữ liệu đã tra cứu ở lượt này; nếu không có thì nói thật là mình chưa có thông tin đó, không tự điền từ trí nhớ.
- Kiến thức sức khỏe phổ thông, ít rủi ro (ăn uống, sinh hoạt, mẹo nhớ uống thuốc, giải thích chung về một bệnh) thì được chia sẻ ngắn gọn, thận trọng, và nhắc hỏi bác sĩ khi phù hợp.
- Nếu người dùng nhắc tới ý muốn chết hay tự làm hại bản thân, đã uống quá nhiều thuốc, hoặc có triệu chứng nặng (khó thở, đau ngực, ngất, co giật, sưng mặt hoặc môi, nôn ra máu...): thể hiện sự quan tâm, khuyên gọi cấp cứu 115 hoặc đến cơ sở y tế gần nhất ngay, và ở cạnh người thân; không trì hoãn bằng câu hỏi dài.
- Không nhắc tới tên nhà cung cấp mô hình AI đứng sau Capy."""


# Natural-tone v1: the synthesis model used to receive raw UTC timestamps and
# raw status codes, and printed them verbatim ("lúc 01:00, trạng thái TAKEN"
# for an 08:00 dose already taken). Only the copy serialized into the
# synthesis prompt is rewritten -- the tool results themselves (audit,
# telemetry, suggested actions, state) are never touched.
_PATIENT_TZ = ZoneInfo(PATIENT_TIMEZONE)
_LOCALIZED_TIME_KEYS = frozenset({"scheduled_at", "window_start", "window_end"})
# Same wording as the deterministic schedule replies (orchestrator).
_DOSE_STATUS_VI = DOSE_STATUS_LABELS_VI


def _localize_for_patient(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {k: _localize_for_patient(v, key=k) for k, v in value.items()}
    if isinstance(value, list):
        return [_localize_for_patient(v) for v in value]
    if isinstance(value, str) and key in _LOCALIZED_TIME_KEYS:
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return value
        if moment.tzinfo is None:
            return value
        return moment.astimezone(_PATIENT_TZ).strftime("%H:%M ngày %d/%m/%Y (giờ Việt Nam)")
    if isinstance(value, str) and key == "status" and value in _DOSE_STATUS_VI:
        return _DOSE_STATUS_VI[value]
    return value


# C2/E1: the model cites inline as "([nhs.uk](https://...))"; the runtime
# lists the sources once at the end instead (drug_evidence.with_web_sources).
_INLINE_SOURCE_RE = re.compile(r"\s*\(\[[^\]]*\]\(https?://[^)\s]*\)\)")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(https?://[^)\s]*\)")
_TRACKING_PARAM_RE = re.compile(r"^(utm_|trk$|fbclid$|gclid$)")


def _strip_inline_sources(text: str) -> str:
    return _MARKDOWN_LINK_RE.sub(r"\1", _INLINE_SOURCE_RE.sub("", text)).strip()


def _clean_source_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if not _TRACKING_PARAM_RE.match(key)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


class OpenAIModelGateway:
    """OpenAI implementation selected by settings, with no frontend key surface."""

    def __init__(
        self,
        workloads: dict[ModelRole, ModelWorkload],
        *,
        client_factory: Callable[..., Any] = openai.OpenAI,
        request_timeout_seconds: float = 15.0,
        web_search_allowed_domains: tuple[str, ...] = (),
    ) -> None:
        self._workloads = workloads
        self._client_factory = client_factory
        self._request_timeout_seconds = request_timeout_seconds
        self._web_search_allowed_domains = web_search_allowed_domains

    @classmethod
    def from_settings(cls, settings: Any) -> OpenAIModelGateway:
        return cls(
            build_model_workloads(settings),
            request_timeout_seconds=float(getattr(settings, "agent_model_timeout_seconds", 15.0)),
            web_search_allowed_domains=tuple(getattr(settings, "agent_web_search_domains", ())),
        )

    def _client_for(self, role: ModelRole) -> Any:
        workload = self._workloads[role]
        if not workload.api_key:
            raise MissingModelCredentialError(
                f"{workload.preferred_credential_env} (or OPENAI_API_KEY for local development) is required"
            )
        return openai_client(workload.api_key, timeout=self._request_timeout_seconds, factory=self._client_factory)

    def _reasoning_kwargs(self, role: ModelRole) -> dict[str, Any]:
        return reasoning_kwargs(self._workloads[role].reasoning_effort)

    def route_read_only(self, *, message: str, actor_role: str) -> str:
        """Return a typed router intent; this is not yet wired into runtime flow."""

        workload = self._workloads[ModelRole.ROUTER]
        response = self._client_for(ModelRole.ROUTER).responses.create(
            model=workload.model,
            input=(
                "Classify this authorized Agent V2 read-only request. Return a concise intent only. "
                f"Actor role: {actor_role}. Request: {message}"
            ),
            text={"format": {"type": "json_schema", "name": "agent_router", "strict": True, "schema": _ROUTER_SCHEMA}},
        )
        parsed = json.loads(str(_value(response, "output_text", "{}")))
        return str(parsed["intent"])

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        """Ask only the Main workload for calls from the six-read-tool allowlist.

        The flag-gated endpoint remains disabled by default.  This first turn
        never has write capability.  ``response`` here is the pre-tool
        planning text only -- the runtime does not use it as the final reply
        once ``tool_calls`` is non-empty; see ``synthesize_read_only`` below
        and ``ReadOnlyAgentRuntime`` (BUILD-19B), which runs it as the
        required second turn after tool execution.
        """

        workload = self._workloads[ModelRole.MAIN]
        response = self._client_for(ModelRole.MAIN).responses.create(
            model=workload.model,
            instructions=_CAPY_SYSTEM_INSTRUCTIONS,
            input=(
                "You are an Agent V2 read-only planner. Use only supplied read tools when data is needed. "
                # Natural-tone v1: when no tool is called, THIS turn's text is
                # the patient's reply, so it must answer like Capy, not decline.
                "Greetings, thanks, small talk, feelings, encouragement, adherence tips (how to remember "
                "doses) and low-risk general wellness questions need no tool: answer them directly, "
                "warmly and briefly in Vietnamese as Capy. Use tools whenever the request depends on the "
                "patient's own prescriptions/doses or on facts about a specific drug. "
                "If the question follows up on a drug named earlier in the conversation memory "
                "(e.g. 'uống lúc nào thì tốt?' right after asking about Metformin), call search_drug "
                "with that drug's name -- never answer a drug fact from memory alone. "
                # C2/E1: this planner gets one tool round and never sees a
                # search_drug result, so the two BUILD-24L instructions that used
                # to be here (call get_drug_info with the resolved id; list the
                # candidates when several match) could not be followed -- the
                # model searched, then answered side effects from memory. The
                # runtime now reads the found product's leaflet itself
                # (ReadOnlyAgentRuntime._chain_drug_info_lookups) and the
                # candidate question moved to the synthesis turn below.
                "For any question about a specific drug, call search_drug with the drug's name; the "
                "system then reads that product's leaflet for you. Call get_drug_info only with a "
                "legacy_drug_id already present in this request -- never guess an id. "
                # BUILD-27B: get_doses_for_range answers a specific resolved
                # past/future date or week; get_today_doses/get_upcoming_doses
                # only ever cover exactly today or a short rolling forward
                # window and must not be used for a named date beyond that.
                "For a question naming a specific past date, a future date beyond "
                "tomorrow, or a week ('tuần trước'/'tuần tới'), call get_doses_for_range, "
                "not get_today_doses or get_upcoming_doses -- the server has already fixed "
                "the exact date/range for this request before you see it. Never state or "
                "compute your own date/range for that call; it takes no arguments. If the "
                "request is about a FUTURE date/range, never phrase the reply as though the "
                "dose has already happened -- say what is scheduled, not what was taken. "
                "Never propose prescription changes, dose-state writes, or clinical advice. "
                f"Authorized actor role: {actor_role}. Request: {message}"
            ),
            tools=list(_READ_ONLY_TOOL_SCHEMAS),
            **self._reasoning_kwargs(ModelRole.MAIN),
        )
        calls: list[ToolCall] = []
        for item in _value(response, "output", ()):
            if _value(item, "type") != "function_call":
                continue
            arguments = json.loads(str(_value(item, "arguments", "{}")))
            if not isinstance(arguments, dict):
                raise ValueError("MODEL_TOOL_ARGUMENTS_INVALID")
            calls.append(ToolCall(name=str(_value(item, "name", "")), arguments=arguments))
        return ModelPlan(
            tool_calls=tuple(calls),
            response=str(_value(response, "output_text", "")),
            usage=_usage(response),
            request_id=_request_id(response),
        )

    def synthesize_read_only(
        self,
        *,
        message: str,
        actor_role: str,
        evidence: tuple[SynthesisEvidence, ...],
        policy: ResponsePolicy | None = None,
        fact_slots: RenderableFactSlots | None = None,
    ) -> ModelSynthesis:
        """Turn already-executed, already-verified tool evidence into final reply text.

        This is the second turn of the tool-calling loop
        (User -> Model -> Tool Call -> Tool Result -> Model Synthesis -> Final
        Reply). It is intentionally called with no ``tools=`` schema at all,
        so the model structurally cannot call another tool or otherwise act
        here -- it can only phrase the evidence the runtime already fetched
        and verified into a reply. The prompt additionally instructs the
        model never to contradict or override Safety/Doctor/Operational DB
        provenance; the runtime never sends unresolved-safety evidence to
        this turn in the first place (see ``ReadOnlyAgentRuntime``).

        TASK-V2.5-004 (CP1 contract mục 4a): ``policy``/``fact_slots`` are
        optional and additive. `None` (every caller before this task, and
        every caller today while ``AGENT_V2_5_RENDERER_ENABLED`` is off) hits
        the branch below unchanged -- ModelRole.MAIN, the reply is the whole
        final text. Passing a real ``policy``/``fact_slots`` switches to
        ModelRole.RENDERER (gpt-5.6-luna) and asks only for ``free_prose``;
        the runtime -- never this method -- is what calls
        ``response_policy.assemble_reply`` afterward to insert the protected
        fact strings verbatim.
        """

        if policy is not None and fact_slots is not None:
            return self._synthesize_free_prose(
                message=message, actor_role=actor_role, evidence=evidence, policy=policy, fact_slots=fact_slots
            )

        workload = self._workloads[ModelRole.MAIN]
        serialized_evidence = json.dumps(
            [{"tool": item.tool_name, "provenance": item.provenance, "data": _localize_for_patient(item.data)} for item in evidence],
            ensure_ascii=False,
        )
        response = self._client_for(ModelRole.MAIN).responses.create(
            model=workload.model,
            instructions=_CAPY_SYSTEM_INSTRUCTIONS,
            input=(
                "You are an Agent V2 read-only assistant. The tool calls you requested have "
                "already run; the results below are verified and authoritative. Treat them as "
                "ground truth and never contradict, override, or second-guess a Safety, Doctor, "
                "or Operational DB provenance entry. Do not invent facts beyond this evidence. "
                # BUILD-24L (found in Phase 2's real golden retest, report 44, golden
                # query_id 45): a reply opened "Minh da ghi nhan: ban da uong thuoc..."
                # ("I've recorded: you took...") for the patient's own unverified claim
                # in their message -- Agent V2 is read-only and never persists any
                # input at all, so this implies a write action that never happened.
                "NEVER say the patient's own message/claim has been recorded, logged, "
                "noted, or saved anywhere -- this agent is read-only and does not "
                "persist any input. Only describe something as 'recorded'/'on file' if "
                "it is actually present in the verified tool evidence above; a "
                "patient's own statement in their message is not itself a recorded fact "
                "just because you are responding to it. "
                "PROVENANCE RULE (BUILD-24B): only describe information as coming from Vinmec if "
                "the evidence below actually carries Vinmec Web provenance -- the user's own "
                "wording mentioning Vinmec is never sufficient grounds by itself. Internal/"
                "canonical drug catalog data (e.g. provenance starting with 'canonical-drug-v2') "
                "and internal RAG retrieval data must always be described as internal or "
                "verified system data, never as Vinmec. If nothing here is genuinely Vinmec-"
                "sourced and the request specifically asked about Vinmec, say honestly that no "
                "Vinmec result was found rather than substituting another source under that name. "
                # BUILD-27B/28: a pure schedule/history question (past,
                # today, or future) is answered deterministically in code,
                # before this turn is ever reached -- see
                # AgentOrchestrator._schedule_reply -- so any dose-schedule
                # tool evidence this turn *does* see (e.g. incidental to an
                # unrelated question) is never past-dated, and "already
                # taken" phrasing here would always be describing something
                # that has not happened yet.
                # C2/E1: leaflet rows come from one product the runtime picked
                # for the drug the patient named (see drug_evidence.py).
                "Drug leaflet rows (get_drug_info) come from one catalog product containing the drug "
                "asked about: answer about the drug itself, and if you mention a dose amount say it is "
                "for that product. If the matched products are genuinely different drugs (not just "
                "brands or strengths of one drug), ask which one the patient means. If the evidence does "
                "not answer the question, say so honestly instead of using outside knowledge. "
                "If the verified evidence is about doses scheduled for today or a future "
                "date, describe them as scheduled/upcoming -- never say or imply the patient "
                "has already taken a dose that has not occurred yet. "
                "Write the final natural-language reply for the authorized actor in Vietnamese. "
                f"Authorized actor role: {actor_role}. Original request: {message}. "
                f"Verified tool evidence (JSON): {serialized_evidence}"
            ),
            **self._reasoning_kwargs(ModelRole.MAIN),
        )
        text = str(_value(response, "output_text", "")).strip()
        if not text:
            # Fail closed through the same bounded-retry path as plan_read_only
            # rather than silently returning empty text again.
            raise EmptySynthesisError("MODEL_SYNTHESIS_EMPTY")
        return ModelSynthesis(free_prose=text, usage=_usage(response), request_id=_request_id(response))

    def answer_with_web_search(
        self,
        *,
        message: str,
        actor_role: str,
        evidence: tuple[SynthesisEvidence, ...] = (),
    ) -> WebAnswer:
        """C2/E1 (MVP): answer from the hosted web search when internal data
        had nothing. ``tool_choice="required"`` forces a real search; the
        search is limited to ``web_search_allowed_domains`` when configured
        (reputable medical sites by default, see Settings)."""

        workload = self._workloads[ModelRole.MAIN]
        web_tool: dict[str, Any] = {"type": "web_search"}
        if self._web_search_allowed_domains:
            web_tool["filters"] = {"allowed_domains": list(self._web_search_allowed_domains)}
        internal = json.dumps(
            [{"tool": item.tool_name, "data": _localize_for_patient(item.data)} for item in evidence], ensure_ascii=False
        )
        response = self._client_for(ModelRole.MAIN).responses.create(
            model=workload.model,
            instructions=_CAPY_SYSTEM_INSTRUCTIONS,
            input=(
                "CapyMedi's internal data has no verified answer for this request, so search the web "
                "and answer from reputable medical sources. Base every medical fact on what the search "
                "returns, never on memory alone. If the results do not answer it (for example the drug "
                "name cannot be found), say so honestly and suggest checking the name on the package or "
                "asking a pharmacist. Search queries must contain only the medical terms of the question "
                "-- never a name or any personal detail. Reply briefly and naturally in Vietnamese as "
                "Capy. Do not put URLs, links or source names in the text; the system lists the sources. "
                f"Authorized actor role: {actor_role}. Internal lookups so far (JSON): {internal}. "
                f"Request: {message}"
            ),
            tools=[web_tool],
            tool_choice="required",
            **self._reasoning_kwargs(ModelRole.MAIN),
        )
        searched = False
        citations: dict[str, dict[str, str]] = {}
        for item in _value(response, "output", ()):
            kind = _value(item, "type")
            if kind == "web_search_call":
                searched = True
            elif kind == "message":
                for content in _value(item, "content", ()) or ():
                    for annotation in _value(content, "annotations", ()) or ():
                        url = _value(annotation, "url")
                        if _value(annotation, "type") == "url_citation" and url:
                            clean = _clean_source_url(str(url))
                            citations.setdefault(clean, {"title": str(_value(annotation, "title", "") or ""), "url": clean})
        return WebAnswer(
            text=_strip_inline_sources(str(_value(response, "output_text", ""))),
            citations=tuple(citations.values()),
            searched=searched,
            usage=_usage(response),
            request_id=_request_id(response),
        )

    def _synthesize_free_prose(
        self,
        *,
        message: str,
        actor_role: str,
        evidence: tuple[SynthesisEvidence, ...],
        policy: ResponsePolicy,
        fact_slots: RenderableFactSlots,
    ) -> ModelSynthesis:
        """TASK-V2.5-004 renderer turn (ModelRole.RENDERER, gpt-5.6-luna).

        Owner correction (post first-draft CP2): an earlier version of this
        method showed the model full raw ``evidence`` plus every populated
        fact-slot value "for context", relying on a prompt instruction not
        to restate them -- exactly the WEAK, model-compliance-dependent
        guarantee mục 4a exists to avoid (the model could still see and
        therefore still paraphrase a fact). Fixed: the model receives ONLY
        ``RendererContext`` (``response_policy.build_renderer_context``) --
        an allowlisted, low-risk-only projection of ``evidence`` with no
        specific claim value in it at all. No ``tools=`` schema either --
        same structural no-tool-call guarantee as the MAIN synthesis turn.

        Independent second layer: ``response_policy.validate_free_prose``
        runs on the model's own output before it is ever returned -- a model
        that hallucinates a prohibited claim from nothing (never having seen
        a fact value) is rejected here, raising ``ProhibitedClaimLeakError``
        instead of silently letting the caller pass it to ``assemble_reply``.
        """

        # Lazy import: response_policy.py imports SynthesisEvidence from
        # this module at its own top level, so a module-level import here
        # would be circular. By call time both modules are fully loaded.
        from backend.agents.v2.response_policy import build_renderer_context, validate_free_prose

        workload = self._workloads[ModelRole.RENDERER]
        context = build_renderer_context(evidence)
        response = self._client_for(ModelRole.RENDERER).responses.create(
            model=workload.model,
            instructions=_CAPY_SYSTEM_INSTRUCTIONS,
            input=(
                "You are the Agent V2 natural-language renderer. Your ONLY job is to write "
                "short connective/empathetic Vietnamese prose (free_prose) -- you never state a "
                "specific dose time, dose status, medication identity, or handoff/doctor-transfer "
                "claim; the backend inserts any of those separately, verbatim, after your text. "
                "You have NOT been given any such fact value here on purpose -- do not guess or "
                "invent one. Never propose prescription changes, dose-state writes, or clinical "
                "advice. "
                f"Whether relevant results were found for this request: {context.has_findings}. "
                f"Route category: {policy.route_category}. Answerability: {policy.answerability.value}. "
                f"Authorized actor role: {actor_role}. Original request: {message}."
            ),
        )
        text = str(_value(response, "output_text", "")).strip()
        if not text:
            raise EmptySynthesisError("MODEL_SYNTHESIS_EMPTY")
        is_valid, violated_categories = validate_free_prose(policy, fact_slots, text)
        if not is_valid:
            raise ProhibitedClaimLeakError(f"PROHIBITED_CLAIM_LEAK:{','.join(violated_categories)}")
        return ModelSynthesis(free_prose=text, usage=_usage(response), request_id=_request_id(response))

    def embed_query(self, *, text: str) -> EmbeddingResult:
        """Embed one retrieval query through the configured EMBEDDING workload."""
        workload = self._workloads[ModelRole.EMBEDDING]
        response = self._client_for(ModelRole.EMBEDDING).embeddings.create(model=workload.model, input=[text])
        data = _value(response, "data", ())
        vector = _value(data[0], "embedding") if data else None
        if not isinstance(vector, (list, tuple)) or not vector:
            raise ValueError("EMBEDDING_EMPTY")
        try:
            normalized = tuple(float(value) for value in vector)
        except (TypeError, ValueError) as exc:
            raise ValueError("EMBEDDING_INVALID") from exc
        return EmbeddingResult(workload.model, normalized, _usage(response), _request_id(response))

    def smoke_all(self) -> tuple[ModelSmokeResult, ...]:
        """Run minimal live endpoint checks after all credentials pass preflight."""

        missing = missing_model_credentials(self._workloads)
        if missing:
            raise MissingModelCredentialError(", ".join(missing) + " (or OPENAI_API_KEY for local development) is required")
        return tuple(self._smoke(role) for role in ModelRole)

    def _smoke(self, role: ModelRole) -> ModelSmokeResult:
        workload = self._workloads[role]
        started = time.perf_counter()
        try:
            client = self._client_for(role)
            if role is ModelRole.ROUTER:
                response = client.responses.create(
                    model=workload.model,
                    input="Return a smoke-test intent.",
                    text={"format": {"type": "json_schema", "name": "build2_router", "strict": True, "schema": _ROUTER_SCHEMA}},
                )
                parsed = json.loads(str(_value(response, "output_text", "{}")))
                if not isinstance(parsed.get("intent"), str):
                    raise ValueError("ROUTER_STRUCTURED_OUTPUT_INVALID")
            elif role is ModelRole.MAIN:
                response = client.responses.create(
                    model=workload.model,
                    input="Use the supplied search_drug tool for the query para.",
                    tools=[_READ_ONLY_TOOL_SCHEMAS[0]],
                    tool_choice={"type": "function", "name": "search_drug"},
                    **self._reasoning_kwargs(ModelRole.MAIN),
                )
                if not any(_value(item, "type") == "function_call" and _value(item, "name") == "search_drug" for item in _value(response, "output", ())):
                    raise ValueError("MAIN_TOOL_CALL_NOT_RETURNED")
            elif role is ModelRole.EMBEDDING:
                response = client.embeddings.create(model=workload.model, input=["BUILD-2 smoke test"])
                if not _value(response, "data"):
                    raise ValueError("EMBEDDING_EMPTY")
            else:
                response = client.responses.create(model=workload.model, input="Reply with the single word OK.")
                if not str(_value(response, "output_text", "")).strip():
                    raise ValueError("TEXT_OUTPUT_EMPTY")
            return ModelSmokeResult(role, workload.model, True, (time.perf_counter() - started) * 1000, _usage(response), _request_id(response))
        except Exception as error:
            return ModelSmokeResult(
                role,
                workload.model,
                False,
                (time.perf_counter() - started) * 1000,
                ModelUsage(),
                error=_safe_error(error),
            )
