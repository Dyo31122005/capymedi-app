"""C2/E1: drug answers come from the leaflet or the web, never model memory.

* The runtime chains ``get_drug_info`` after ``search_drug`` (the planner has
  one tool round and get_drug_info needs the id search_drug returns).
* When the catalog has no facts for a named drug, or a strictly grounded
  general question gathered nothing, the Main Model answers from its hosted
  web search (MVP: a trusted source) and the reply lists the sources.
* The grounding backstop counts a bare catalog search as no evidence.
"""

from __future__ import annotations

import pytest

from backend.agents.v2.drug_evidence import (
    compact_leaflet,
    has_drug_facts,
    has_fact_evidence,
    needs_web_evidence,
    representative_drug_ids,
    with_web_sources,
)
from backend.agents.v2.handoff import DoctorHandoffGateway
from backend.agents.v2.model_gateway import (
    ModelPlan,
    ModelSynthesis,
    OpenAIModelGateway,
    ToolCall,
    WebAnswer,
    build_model_workloads,
)
from backend.agents.v2.orchestrator import (
    _DRUG_INFO_DISCLAIMER,
    _UNGROUNDED_ANSWER_DECLINE_REPLY,
    AgentOrchestrator,
    OrchestrationIntent,
    classify_intent,
)
from backend.agents.v2.runtime import ReadOnlyAgentRuntime, RunStatus
from backend.agents.v2.safety import SafetyGateway
from backend.agents.v2.tools import AuthorizedToolContext, ToolGateway, ToolResult
from tests.test_agent_v2_model_gateway import _settings
from tests.test_agent_v2_orchestrator import (
    NOW,
    _context_manager,
    _IdempotentHandoffDomain,
    _limits,
    _request,
    _safety_decision,
    _SafetyDomain,
    _SpyModelGateway,
)

_LONG = "x " * 1000


def _search(*items: dict, unique: str | None = None) -> dict:
    return {"items": list(items), "unique_match_legacy_drug_id": unique}


def _item(drug_id: str, name: str, route: str = "Uống") -> dict:
    return {"legacy_drug_id": drug_id, "name": name, "dosage_form": "Viên nén", "route": route, "strength": "5mg"}


# -- representative_drug_ids ----------------------------------------------------


def test_unique_catalog_match_wins():
    data = _search(_item("a", "Amlodipine Stada 5mg"), _item("b", "Amlodipine Stada 10mg"), unique="b")
    assert representative_drug_ids("Amlodipine Stada 10mg", data) == ["b"]


def test_ingredient_match_prefers_oral_products_and_keeps_catalog_rank():
    data = _search(
        _item("inj", "Atimezon INJ Omeprazole 40mg", route="Tiêm"),
        _item("o1", "Omeprazole 20mg Brawn"),
        _item("eso", "SAVI Esomeprazole 40mg"),
        _item("o2", "Omeprazol 20mg DHG"),
    )
    # Vietnamese spelling (omeprazol) matches the INN; esomeprazole is another molecule.
    assert representative_drug_ids("omeprazole", data) == ["o1", "o2", "inj"]


@pytest.mark.parametrize("query", ["thuốc chống trầm cảm", "para", "thuoc huyet ap"])
def test_class_or_fragment_queries_pick_nothing(query):
    data = _search(_item("x", "Chống say xe Nam Hà"), _item("p", "Paracetamol 500mg"), _item("h", "Huyết áp ABC"))
    assert representative_drug_ids(query, data) == []


def test_a_fuzzy_catalog_neighbour_is_not_the_searched_drug():
    data = _search(_item("pi", "Piracetam KABI 12g"), _item("re", "Relestat 5ml"))
    assert representative_drug_ids("Paracetamol", data) == []


# -- compact_leaflet / evidence predicates ----------------------------------------


def _leaflet(drug_id: str, *contents: str) -> ToolResult:
    rows = [{"field": "tac_dung_phu", "content": content, "source": f"ADVERSE_EFFECT - {drug_id}"} for content in contents]
    return ToolResult(name="get_drug_info", data={"legacy_drug_id": drug_id, "results": rows, "trace": {}})


def test_compact_leaflet_trims_long_rows_and_drops_rows_already_shown():
    seen: set[str] = set()
    first = compact_leaflet(_leaflet("a", "Đau đầu, chóng mặt.", _LONG), seen)
    assert first is not None
    contents = [row["content"] for row in first.data["results"]]
    assert contents[0] == "Đau đầu, chóng mặt."
    assert len(contents[1]) <= 1202 and contents[1].endswith("…")
    assert compact_leaflet(_leaflet("b", "Đau đầu, chóng mặt."), seen) is None
    assert compact_leaflet(_leaflet("c"), set()) is None


def test_a_bare_search_or_an_empty_leaflet_is_not_fact_evidence():
    search = ToolResult(name="search_drug", data=_search(_item("a", "Amlodipine")))
    empty = _leaflet("a")
    assert not has_fact_evidence([search, empty])
    assert not has_drug_facts([search, empty])
    assert needs_web_evidence([search, empty], evidence_required=False)
    assert has_fact_evidence([search, _leaflet("a", "Ho, khó thở.")])
    assert has_fact_evidence([ToolResult(name="get_today_doses", data={"items": []})])
    assert has_drug_facts([ToolResult(name="web_search", data={"citations": []})])
    assert needs_web_evidence([], evidence_required=True)
    assert not needs_web_evidence([], evidence_required=False)


def test_web_sources_are_listed_once_by_site():
    text = with_web_sources("Có thể gây loét.", [{"title": "Ibuprofen - NHS", "url": "https://www.nhs.uk/medicines/ibuprofen/"}])
    assert text == "Có thể gây loét.\n\nNguồn tham khảo: [nhs.uk](https://www.nhs.uk/medicines/ibuprofen/)"
    assert with_web_sources("abc", []) == "abc"


# -- runtime: chained lookup + web fallback ------------------------------------------


class _CatalogTools:
    def __init__(self, items: list[dict], leaflets: dict[str, list[str]]) -> None:
        self.items = items
        self.leaflets = leaflets
        self.calls: list[tuple[str, str]] = []

    def search_drug(self, *, query: str, limit: int) -> dict:
        self.calls.append(("search_drug", query))
        return _search(*self.items)

    def get_drug_info(self, *, legacy_drug_id: str, query: str) -> dict:
        self.calls.append(("get_drug_info", legacy_drug_id))
        if legacy_drug_id not in self.leaflets:
            raise LookupError("unknown drug id")
        rows = [{"field": "tac_dung_phu", "content": c, "source": f"X - {legacy_drug_id}"} for c in self.leaflets[legacy_drug_id]]
        return {"legacy_drug_id": legacy_drug_id, "results": rows, "trace": {}}


class _WebGateway(_SpyModelGateway):
    def __init__(self, plan, synthesis=None, *, web: WebAnswer | Exception | None = None) -> None:
        super().__init__(plan, synthesis or ModelSynthesis(free_prose="from leaflet"))
        self.web = web or WebAnswer(
            text="Ibuprofen có thể gây kích ứng dạ dày.",
            citations=({"title": "Ibuprofen | Vinmec", "url": "https://www.vinmec.com/vie/thuoc/ibuprofen-99"},),
            searched=True,
        )
        self.web_calls: list[dict] = []

    def answer_with_web_search(self, *, message, actor_role, evidence=()):
        self.web_calls.append({"message": message, "evidence": evidence})
        if isinstance(self.web, Exception):
            raise self.web
        return self.web


def _tools(domain) -> ToolGateway:
    return ToolGateway(domain, context=AuthorizedToolContext(actor_id="actor-1", actor_role="patient", patient_id="patient-1"))


def _search_plan(*queries: str) -> ModelPlan:
    return ModelPlan(tool_calls=tuple(ToolCall("search_drug", {"query": q, "limit": 5}) for q in queries), response="")


def _runtime(gateway, *, web=True, **limits) -> ReadOnlyAgentRuntime:
    return ReadOnlyAgentRuntime(gateway, limits=_limits(**({"max_steps": 6, "max_tool_calls": 6} | limits)), web_search_enabled=web)


def test_runtime_reads_the_leaflet_of_the_searched_drug_before_synthesis():
    domain = _CatalogTools([_item("aml-5", "Amlodipine Stada 5mg"), _item("aml-10", "Amlodipine Stada 10mg")], {"aml-5": ["Ho (ít gặp). " * 200]})
    gateway = _WebGateway(_search_plan("Amlodipine"))

    result = _runtime(gateway).run(message="Amlodipine có gây ho không?", actor_role="patient", tools=_tools(domain), lookup_query="Amlodipine có gây ho không?")

    assert result.status is RunStatus.COMPLETED
    assert result.response == "from leaflet"
    # A rich first leaflet: the second product of the same molecule is not read.
    assert domain.calls == [("search_drug", "Amlodipine"), ("get_drug_info", "aml-5")]
    assert [e.tool_name for e in gateway.synthesis_calls[0]["evidence"]] == ["search_drug", "get_drug_info"]
    assert gateway.web_calls == []
    assert result.metrics.tool_calls == 2


def test_a_thin_first_leaflet_reads_a_second_product_and_a_failed_lookup_is_skipped():
    domain = _CatalogTools(
        [_item("met-x", "Metformin X"), _item("met-a", "Metformin Boston 850"), _item("met-b", "Metformin Stella 1000")],
        {"met-a": ["Quá mẫn."], "met-b": ["Suy gan thận: thận trọng."]},
    )
    gateway = _WebGateway(_search_plan("Metformin"))

    result = _runtime(gateway).run(message="Metformin có hại thận không?", actor_role="patient", tools=_tools(domain))

    assert result.status is RunStatus.COMPLETED
    # met-x raises (skipped, budget kept); met-a is thin, so met-b is read too... within 2 per drug.
    assert ("get_drug_info", "met-x") in domain.calls and ("get_drug_info", "met-a") in domain.calls
    assert sum(1 for name, _ in domain.calls if name == "get_drug_info") == 2


def test_two_drugs_each_get_a_leaflet_within_the_step_budget():
    domain = _CatalogTools([_item("los", "Losartan 50mg"), _item("aml", "Amlodipine 5mg")], {"los": ["A " * 900], "aml": ["B " * 900]})
    gateway = _WebGateway(_search_plan("Losartan", "Amlodipine"))

    result = _runtime(gateway).run(message="Losartan với Amlodipine khác nhau thế nào?", actor_role="patient", tools=_tools(domain))

    assert result.status is RunStatus.COMPLETED
    looked_up = [drug_id for name, drug_id in domain.calls if name == "get_drug_info"]
    assert looked_up == ["los", "aml"]
    assert result.metrics.steps <= 6


def test_a_drug_missing_from_the_catalog_is_answered_from_the_web_with_sources():
    domain = _CatalogTools([], {})
    gateway = _WebGateway(_search_plan("Ibuprofen"))

    result = _runtime(gateway).run(message="Ibuprofen có hại dạ dày không", actor_role="patient", tools=_tools(domain))

    assert result.status is RunStatus.COMPLETED
    assert result.response.startswith("Ibuprofen có thể gây kích ứng dạ dày.")
    assert "Nguồn tham khảo: [vinmec.com](https://www.vinmec.com/vie/thuoc/ibuprofen-99)" in result.response
    assert [t.name for t in result.tool_results] == ["search_drug", "web_search"]
    assert gateway.synthesis_calls == []  # the web answer replaces synthesis
    assert result.metrics.model_calls == 2


def test_web_search_disabled_keeps_the_ordinary_synthesis():
    gateway = _WebGateway(_search_plan("Ibuprofen"))
    result = _runtime(gateway, web=False).run(message="Ibuprofen?", actor_role="patient", tools=_tools(_CatalogTools([], {})))
    assert result.response == "from leaflet" and gateway.web_calls == []


@pytest.mark.parametrize(
    "web", [RuntimeError("boom"), WebAnswer(text="trả lời từ trí nhớ", searched=False), WebAnswer(text="", searched=True)]
)
def test_a_failed_or_ungrounded_web_answer_falls_back_to_synthesis(web):
    gateway = _WebGateway(_search_plan("Ibuprofen"), web=web)
    result = _runtime(gateway).run(message="Ibuprofen?", actor_role="patient", tools=_tools(_CatalogTools([], {})))
    assert result.status is RunStatus.COMPLETED
    assert result.response == "from leaflet"
    assert [t.name for t in result.tool_results] == ["search_drug"]


def test_an_evidence_required_question_with_no_tool_call_is_answered_from_the_web():
    gateway = _WebGateway(ModelPlan(response="trả lời từ trí nhớ"))
    result = _runtime(gateway).run(message="q", actor_role="patient", tools=_tools(_CatalogTools([], {})), evidence_required=True)
    assert [t.name for t in result.tool_results] == ["web_search"]
    assert "trí nhớ" not in result.response


def test_a_flexible_question_with_no_tool_call_never_searches_the_web():
    gateway = _WebGateway(ModelPlan(response="Bạn thử đặt báo thức nhé."))
    result = _runtime(gateway).run(message="làm sao nhớ uống thuốc", actor_role="patient", tools=_tools(_CatalogTools([], {})))
    assert result.response == "Bạn thử đặt báo thức nhé." and gateway.web_calls == []


# -- orchestrator wiring ------------------------------------------------------------


def _orchestrator(gateway, *, web=True) -> AgentOrchestrator:
    return AgentOrchestrator(
        runtime=_runtime(gateway, web=web),
        context_manager=_context_manager(),
        safety_gateway=SafetyGateway(_SafetyDomain(_safety_decision()), timeout_seconds=5.0),
        handoff_gateway=DoctorHandoffGateway(_IdempotentHandoffDomain()),
        now=lambda: NOW,
    )


def test_orchestrator_turns_web_sources_into_citations_and_keeps_the_answer():
    gateway = _WebGateway(_search_plan("Ibuprofen"))
    result = _orchestrator(gateway).run(_request("Ibuprofen có hại dạ dày không"), tools=_tools(_CatalogTools([], {})))

    assert result.status is RunStatus.COMPLETED
    assert result.error_code is None
    assert [(c.source, c.url) for c in result.citations] == [("vinmec-web", "https://www.vinmec.com/vie/thuoc/ibuprofen-99")]
    assert result.response.endswith(_DRUG_INFO_DISCLAIMER)
    # The patient's own question (not the memory-augmented prompt) is what was looked up.
    assert gateway.web_calls


def test_orchestrator_declines_a_drug_answer_with_no_facts_when_the_web_is_off():
    gateway = _WebGateway(_search_plan("Amlodipine"), ModelSynthesis(free_prose="Amlodipine không gây ho."))
    domain = _CatalogTools([_item("aml", "Amlodipine 5mg")], {"aml": []})
    result = _orchestrator(gateway, web=False).run(_request("Amlodipine có gây ho không?"), tools=_tools(domain))

    assert result.intent is OrchestrationIntent.UNKNOWN_OR_AMBIGUOUS
    assert result.error_code == "GROUNDING_FAILURE"
    assert result.response == _UNGROUNDED_ANSWER_DECLINE_REPLY


def test_orchestrator_passes_the_patient_question_to_the_leaflet_lookup():
    domain = _CatalogTools([_item("aml", "Amlodipine 5mg")], {"aml": ["Ho, khó thở (ít gặp)."]})
    queries: list[str] = []
    original = domain.get_drug_info

    def recording_get_drug_info(*, legacy_drug_id, query):
        queries.append(query)
        return original(legacy_drug_id=legacy_drug_id, query=query)

    domain.get_drug_info = recording_get_drug_info
    result = _orchestrator(_WebGateway(_search_plan("Amlodipine"))).run(_request("Amlodipine có gây ho không?"), tools=_tools(domain))

    assert result.status is RunStatus.COMPLETED and result.error_code is None
    assert queries == ["Amlodipine có gây ho không?"]
    assert result.response == f"from leaflet\n\n{_DRUG_INFO_DISCLAIMER}"


def test_stomach_question_is_not_small_talk():
    # "dạ" (polite yes) inside "dạ dày" (stomach) used to route it to GENERAL_CONVERSATION.
    assert classify_intent("Ibuprofen có hại dạ dày không").intent is OrchestrationIntent.UNKNOWN_OR_AMBIGUOUS
    assert classify_intent("dạ vâng ạ").intent is OrchestrationIntent.GENERAL_CONVERSATION


# -- gateway: hosted web search call ------------------------------------------------


class _WebResponses:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _WebClient:
    def __init__(self, response):
        self.responses = _WebResponses(response)


def test_gateway_forces_a_filtered_web_search_and_parses_citations():
    url = "https://www.nhs.uk/medicines/ibuprofen-for-adults/?trk=article-ssr&utm_source=openai"
    response = {
        "output": [
            {"type": "web_search_call", "action": {"type": "search", "query": "ibuprofen stomach"}},
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "...",
                        "annotations": [
                            {"type": "url_citation", "title": "Ibuprofen - NHS", "url": url},
                            {"type": "url_citation", "title": "Ibuprofen - NHS", "url": url},
                        ],
                    }
                ],
            },
        ],
        "output_text": f"Có, ibuprofen có thể gây loét dạ dày. ([nhs.uk]({url}))",
        "usage": {"input_tokens": 8000, "output_tokens": 90},
    }
    client = _WebClient(response)
    gateway = OpenAIModelGateway(
        build_model_workloads(_settings()), client_factory=lambda **_kwargs: client, web_search_allowed_domains=("nhs.uk", "vinmec.com")
    )

    answer = gateway.answer_with_web_search(message="Ibuprofen có hại dạ dày không", actor_role="patient")

    call = client.responses.calls[0]
    assert call["tools"] == [{"type": "web_search", "filters": {"allowed_domains": ["nhs.uk", "vinmec.com"]}}]
    assert call["tool_choice"] == "required"
    assert answer.searched is True
    assert answer.text == "Có, ibuprofen có thể gây loét dạ dày."
    assert answer.citations == ({"title": "Ibuprofen - NHS", "url": "https://www.nhs.uk/medicines/ibuprofen-for-adults/"},)
    assert answer.usage.input_tokens == 8000


def test_gateway_reports_an_answer_without_a_search_as_not_searched():
    client = _WebClient({"output": [{"type": "message", "content": []}], "output_text": "từ trí nhớ", "usage": {}})
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)

    answer = gateway.answer_with_web_search(message="q", actor_role="patient")

    assert answer.searched is False
    assert "filters" not in client.responses.calls[0]["tools"][0]  # no allowlist configured -> any site


# -- #4: a drug question the router missed is reported as DRUG_INFORMATION -------


def test_a_drug_lookup_answer_is_reported_as_drug_information():
    domain = _CatalogTools([_item("aml", "Amlodipine 5mg")], {"aml": ["Ho (ít gặp)."]})
    result = _orchestrator(_WebGateway(_search_plan("Amlodipine"))).run(_request("Amlodipine có gây ho không?"), tools=_tools(domain))
    assert classify_intent("Amlodipine có gây ho không?").intent is OrchestrationIntent.UNKNOWN_OR_AMBIGUOUS
    assert result.intent is OrchestrationIntent.DRUG_INFORMATION


def test_a_declined_or_tool_free_answer_keeps_its_router_intent():
    declined = _orchestrator(_WebGateway(_search_plan("Amlodipine")), web=False).run(
        _request("Amlodipine có gây ho không?"), tools=_tools(_CatalogTools([_item("aml", "Amlodipine 5mg")], {"aml": []}))
    )
    assert declined.intent is OrchestrationIntent.UNKNOWN_OR_AMBIGUOUS
    chat = _orchestrator(_WebGateway(ModelPlan(response="Bạn thử đặt báo thức nhé."))).run(
        _request("làm sao để nhớ uống thuốc đúng giờ"), tools=_tools(_CatalogTools([], {}))
    )
    assert chat.intent is OrchestrationIntent.UNKNOWN_OR_AMBIGUOUS


# -- #3: web answer cache ---------------------------------------------------------


def test_web_cache_key_needs_a_searched_drug_and_hashes_the_exact_model_input():
    from backend.agents.v2.drug_evidence import web_cache_key

    search = [ToolCall("search_drug", {"query": "Amlodipine", "limit": 5})]
    assert web_cache_key("còn trẻ em thì sao?", []) is None
    plain = web_cache_key('{"message": "Amlodipine có dùng được không?"}', search)
    assert plain == web_cache_key('{"message": "Amlodipine có dùng được không?"}', search)
    # Issue #9, blocker 4: patient A's context in the model input -> a key
    # patient B's identical question can never hit.
    with_context = web_cache_key(
        '{"message": "[memory] user: tôi đang mang thai | Amlodipine có dùng được không?"}', search
    )
    assert plain and with_context and plain != with_context


def test_web_answer_cache_expires_and_evicts_oldest():
    from backend.agents.v2.drug_evidence import WebAnswerCache

    now = [0.0]
    cache = WebAnswerCache(ttl_seconds=10, max_entries=2, clock=lambda: now[0])
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)  # evicts "a"
    assert cache.get("a") is None and cache.get("b") == 2 and cache.get(None) is None
    now[0] = 11
    assert cache.get("c") is None


def test_a_repeated_question_reuses_the_cached_web_answer_without_a_model_call():
    from backend.agents.v2.drug_evidence import WebAnswerCache

    cache = WebAnswerCache()
    gateway = _WebGateway(_search_plan("Ibuprofen"))
    runtime = ReadOnlyAgentRuntime(gateway, limits=_limits(max_steps=6, max_tool_calls=6), web_search_enabled=True, web_answer_cache=cache)

    first = runtime.run(message="Ibuprofen có hại dạ dày không", actor_role="patient", tools=_tools(_CatalogTools([], {})))
    second = runtime.run(message="Ibuprofen có hại dạ dày không", actor_role="patient", tools=_tools(_CatalogTools([], {})))

    assert len(gateway.web_calls) == 1
    assert second.response == first.response
    assert second.metrics.model_calls == 1  # planner only
    assert [t.name for t in second.tool_results] == ["search_drug", "web_search"]


def test_an_unusable_web_answer_is_not_cached():
    from backend.agents.v2.drug_evidence import WebAnswerCache

    cache = WebAnswerCache()
    gateway = _WebGateway(_search_plan("Ibuprofen"), web=WebAnswer(text="x", searched=False))
    runtime = ReadOnlyAgentRuntime(gateway, limits=_limits(max_steps=6, max_tool_calls=6), web_search_enabled=True, web_answer_cache=cache)
    for _ in range(2):
        runtime.run(message="Ibuprofen?", actor_role="patient", tools=_tools(_CatalogTools([], {})))
    assert len(gateway.web_calls) == 2


# -- #2: a named catalog drug skips the planner turn --------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Amlodipine có gây ho không?", ("Amlodipine",)),
        ("Losartan với Amlodipine khác nhau thế nào?", ("Losartan", "Amlodipine")),
        ("Panadol extra uống mấy viên", ("Panadol",)),
        ("uống lúc nào thì tốt?", ()),
        ("nguoi gia uong thuoc nhieu co sao khong", ()),
        ("chào Capy", ()),
    ],
)
def test_drug_name_candidates_are_multi_syllable_latin_words(message, expected):
    from backend.agents.v2.drug_evidence import drug_name_candidates

    assert drug_name_candidates(message) == expected


def _prefetch_runtime(gateway, **kwargs) -> ReadOnlyAgentRuntime:
    return ReadOnlyAgentRuntime(
        gateway, limits=_limits(max_steps=6, max_tool_calls=6), web_search_enabled=True, drug_prefetch_enabled=True, **kwargs
    )


def test_a_named_catalog_drug_is_answered_with_one_model_call():
    domain = _CatalogTools([_item("aml", "Amlodipine 5mg")], {"aml": ["Ho (ít gặp)."]})
    gateway = _WebGateway(ModelPlan(response="planner must not run"))

    result = _prefetch_runtime(gateway).run(
        message="Amlodipine có gây ho không?", actor_role="patient", tools=_tools(domain), drug_terms=("Amlodipine",)
    )

    assert result.status is RunStatus.COMPLETED and result.response == "from leaflet"
    assert gateway.calls == []  # no planner turn
    assert result.metrics.model_calls == 1
    assert domain.calls == [("search_drug", "Amlodipine"), ("get_drug_info", "aml")]


def test_a_term_that_is_not_a_catalog_drug_falls_back_to_the_planner():
    domain = _CatalogTools([_item("x", "Vitamin C 500mg")], {})
    gateway = _WebGateway(ModelPlan(response="Trang web Vinmec có nhiều bài viết."))

    result = _prefetch_runtime(gateway).run(message="website vinmec", actor_role="patient", tools=_tools(domain), drug_terms=("website",))

    assert len(gateway.calls) == 1 and result.response == "Trang web Vinmec có nhiều bài viết."
    assert result.tool_results == ()  # the unmatched search is not kept


def test_prefetch_is_off_by_default():
    domain = _CatalogTools([_item("aml", "Amlodipine 5mg")], {"aml": ["Ho."]})
    gateway = _WebGateway(_search_plan("Amlodipine"))
    _runtime(gateway).run(message="Amlodipine?", actor_role="patient", tools=_tools(domain), drug_terms=("Amlodipine",))
    assert len(gateway.calls) == 1


def test_orchestrator_prefetches_only_for_drug_shaped_intents():
    domain = _CatalogTools([_item("aml", "Amlodipine 5mg")], {"aml": ["Ho (ít gặp)."]})
    gateway = _WebGateway(ModelPlan(response="planner"))
    orchestrator = AgentOrchestrator(
        runtime=_prefetch_runtime(gateway),
        context_manager=_context_manager(),
        safety_gateway=SafetyGateway(_SafetyDomain(_safety_decision()), timeout_seconds=5.0),
        handoff_gateway=DoctorHandoffGateway(_IdempotentHandoffDomain()),
        now=lambda: NOW,
    )

    drug = orchestrator.run(_request("Amlodipine có gây ho không?"), tools=_tools(domain))
    assert gateway.calls == [] and drug.intent is OrchestrationIntent.DRUG_INFORMATION

    # TASK-V2.6-001 B: a listing question about the prescription is answered
    # from the prescription rows, with no model turn at all.
    prescription = orchestrator.run(_request("đơn thuốc của tôi có Amlodipine không"), tools=_tools(domain))
    assert prescription.intent is OrchestrationIntent.PRESCRIPTION_INFORMATION
    assert gateway.calls == []


# -- #5: the Judge sees the evidence and scores claim by claim ---------------------


def test_judge_sees_leaflet_rows_and_web_sources_not_just_ids():
    from backend.agents.v2.evaluation_v2 import EvaluationPath
    from backend.agents.v2.judge_input import build_judge_input

    leaflet = _leaflet("aml", "Ho, khó thở (ít gặp).")
    search = ToolResult(name="search_drug", data=_search(_item("aml", "Amlodipine 5mg")))
    web = ToolResult(name="web_search", data={"citations": [{"title": "Ibuprofen | Vinmec", "url": "https://www.vinmec.com/x"}]})

    payload = build_judge_input(query="Amlodipine có gây ho không?", response="Có, ít gặp.", path=EvaluationPath.RAG, tool_results=(search, leaflet, web))

    evidence = " | ".join(payload.retrieved_evidence)
    assert "Ho, khó thở (ít gặp)." in evidence
    assert "name=Amlodipine 5mg" in evidence and "legacy_drug_id" not in evidence
    assert "nguon web: Ibuprofen | Vinmec (https://www.vinmec.com/x)" in evidence


def test_rag_rubric_scores_faithfulness_claim_by_claim():
    from backend.agents.v2.evaluation_v2 import EvaluationPath
    from backend.agents.v2.judge_rubrics import rubric_for_path

    guidance = rubric_for_path(EvaluationPath.RAG).guidance
    assert "THEO TUNG KHANG DINH" in guidance and "unsupported_claim" in guidance and "web_sourced" in guidance
