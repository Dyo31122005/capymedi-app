"""C2/E1: what counts as evidence for a drug answer, and the web fallback.

Two facts drive this module:

* ``search_drug`` only confirms that a product exists in the catalog (name,
  dosage form, route, strength). It is identity evidence, never evidence for
  a side effect, a contraindication or a pregnancy claim. Only
  ``get_drug_info`` rows (the product leaflet) are drug-fact evidence.
* The runtime gives the planner a single tool round, and ``get_drug_info``
  needs a ``legacy_drug_id`` that only ``search_drug`` returns -- so the
  planner can never chain the two itself. ``representative_drug_ids`` picks
  which products the runtime looks up on its behalf.

When the catalog has no facts for a named drug (or a general medical question
has no evidence at all), the runtime asks the Main Model with its hosted web
search tool instead (MVP: treated as a trusted source; see
``ReadOnlyAgentRuntime._answer_from_web``).
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit

from backend.agents.v2.follow_up import _ascii_fold
from backend.agents.v2.tools import ToolName, ToolResult

WEB_SEARCH_TOOL = "web_search"

# Generic words a model may put into a search_drug query next to the name.
_QUERY_STOPWORDS = frozenset({"thuoc", "vien", "loai", "dang", "nhom", "hop", "goi", "chai"})
# A name token matches a query token on its first 6 letters: covers the
# Vietnamese spellings ("amlodipin", "omeprazol") of the INN without matching
# a different molecule ("esomeprazole" does not start with "omepra"). Only
# query tokens of 6+ letters count: drug names are, folded Vietnamese
# syllables mostly are not ("thuốc chống trầm cảm" is a class, not a name).
_STEM_LENGTH = 6
# Leaflet rows can be long (one INTERACTION row is 5,000 chars); the run's
# token budget has to hold the planner turn, the leaflet(s) and the reply.
LEAFLET_ROW_MAX_CHARS = 1200
# A second product of the same drug is read only when the first leaflet is
# this thin -- two leaflets of one molecule are near-identical otherwise.
SECOND_LEAFLET_BELOW_CHARS = 1500
_MAX_SOURCES_SHOWN = 3


def searched_drug(results: Iterable[ToolResult]) -> bool:
    return any(result.name == ToolName.SEARCH_DRUG.value for result in results)


def _is_drug_fact(result: ToolResult) -> bool:
    return result.name == ToolName.GET_DRUG_INFO.value and bool(result.data.get("results"))


def has_drug_facts(results: Iterable[ToolResult]) -> bool:
    return any(_is_drug_fact(result) or result.name == WEB_SEARCH_TOOL for result in results)


def has_fact_evidence(results: Iterable[ToolResult]) -> bool:
    """Any result that can back a factual claim: everything except a bare
    catalog search and an empty leaflet lookup."""
    return any(
        result.name not in (ToolName.SEARCH_DRUG.value, ToolName.GET_DRUG_INFO.value) or _is_drug_fact(result)
        for result in results
    )


def needs_web_evidence(results: Sequence[ToolResult], *, evidence_required: bool) -> bool:
    """A named drug the catalog has no facts for, or an evidence-required
    question that gathered nothing at all."""
    if searched_drug(results) and not has_drug_facts(results):
        return True
    return evidence_required and not results


def representative_drug_ids(query: str, search_data: dict[str, Any]) -> list[str]:
    """Products to read the leaflet of for one ``search_drug`` result: the
    unique match when there is one, otherwise every listed product whose name
    carries the searched ingredient, oral products first (catalog rank kept).
    A general question about an ingredient is answered from a leaflet of a
    product containing it; the model is told which product it was."""
    unique = search_data.get("unique_match_legacy_drug_id")
    if unique:
        return [str(unique)]
    stems = {token[:_STEM_LENGTH] for token in _ascii_fold(query).split() if len(token) >= _STEM_LENGTH and token not in _QUERY_STOPWORDS}
    if not stems:
        return []
    eligible = [
        item
        for item in search_data.get("items") or ()
        if any(token.startswith(stem) for token in _ascii_fold(str(item.get("name", ""))).split() for stem in stems)
    ]
    eligible.sort(key=lambda item: _ascii_fold(str(item.get("route", ""))) != "uong")
    return [str(item["legacy_drug_id"]) for item in eligible if item.get("legacy_drug_id")]


def prescribed_ids_for(query: str, prescribed_ids: Iterable[str]) -> list[str]:
    """The patient's prescribed catalog ids whose slug carries a searched
    ingredient ("metformin-500mg-stella-3x10" for "Metformin")."""
    stems = {token[:_STEM_LENGTH] for token in _ascii_fold(query).split() if len(token) >= _STEM_LENGTH and token not in _QUERY_STOPWORDS}
    if not stems:
        return []
    return [
        drug_id
        for drug_id in prescribed_ids
        if any(part.startswith(stem) for part in re.split(r"[-_\s]+", _ascii_fold(drug_id)) for stem in stems)
    ]


def compact_leaflet(result: ToolResult, seen: set[str]) -> ToolResult | None:
    """A chained ``get_drug_info`` result with long rows trimmed and rows
    already shown by another product dropped; ``None`` when nothing new is
    left (an empty leaflet included)."""
    rows = []
    for row in result.data.get("results") or ():
        content = str(row.get("content", ""))
        if not content or content in seen:
            continue
        seen.add(content)
        if len(content) > LEAFLET_ROW_MAX_CHARS:
            content = content[:LEAFLET_ROW_MAX_CHARS].rsplit(" ", 1)[0] + " …"
        rows.append({**row, "content": content})
    if not rows:
        return None
    return replace(result, data={**result.data, "results": rows})


def leaflet_chars(result: ToolResult) -> int:
    return sum(len(str(row.get("content", ""))) for row in result.data.get("results") or ())


_WORD_RE = re.compile(r"[^\W\d_]+")
_VOWEL_CLUSTER_RE = re.compile(r"[aeiouy]+")


def drug_name_candidates(message: str) -> tuple[str, ...]:
    """#2: words of the message that look like drug names, in order. A
    Vietnamese syllable (folded) has exactly one vowel cluster ("nguoi",
    "thuong"); drug names are multi-syllable Latin words ("amlodipine",
    "metformin", "panadol"). Only a candidate -- the runtime keeps a term
    only when a catalog product actually carries the name."""
    seen: dict[str, None] = {}
    for word in _WORD_RE.findall(message):
        folded = _ascii_fold(word)
        if folded != word.casefold():
            continue  # carries Vietnamese diacritics: a Vietnamese word
        if len(folded) >= _STEM_LENGTH and len(_VOWEL_CLUSTER_RE.findall(folded)) >= 2 and folded not in _QUERY_STOPWORDS:
            seen.setdefault(word, None)
    return tuple(seen)


# -- web answer formatting ------------------------------------------------------


def _source_label(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host.removeprefix("www.") or url


def with_web_sources(text: str, citations: Sequence[dict[str, str]]) -> str:
    if not citations:
        return text
    links = ", ".join(f"[{_source_label(c['url'])}]({c['url']})" for c in citations[:_MAX_SOURCES_SHOWN])
    return f"{text}\n\nNguồn tham khảo: {links}"


def web_citations(results: Iterable[ToolResult]) -> list[dict[str, str]]:
    return [citation for result in results if result.name == WEB_SEARCH_TOOL for citation in result.data.get("citations", ())]


# -- web answer cache -------------------------------------------------------------


def web_cache_key(model_input: str, calls: Iterable[Any]) -> str | None:
    """Cache key for a web answer: a hash of EXACTLY what the model was given.

    Issue #9, blocker 4: the key used to be the bare question + drug names
    while the answer was generated from the augmented message (this patient's
    conversation memory) and this patient's own tool results -- patient B
    asking the same question within 24 h got the answer written for patient A
    ("tôi đang mang thai" + "Amlodipine có dùng được không?"). Hashing the full
    model input means a cached answer is only reused for an identical input,
    which by construction carries no other patient's context.

    ``None`` (never cached) when no drug was searched: such answers depend on
    the conversation rather than on public drug information.
    """
    if not any(call.name == ToolName.SEARCH_DRUG.value for call in calls):
        return None
    return hashlib.sha256(model_input.encode("utf-8")).hexdigest()


class WebAnswerCache:
    """Process-wide TTL cache of usable web answers (MVP: in memory, one per
    worker; a persistent store would need its own table)."""

    def __init__(
        self, *, ttl_seconds: float = 24 * 3600, max_entries: int = 512, clock: Callable[[], float] | None = None
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str | None) -> Any | None:
        if key is None:
            return None
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._clock() - entry[0] > self._ttl:
                del self._entries[key]
                return None
            return entry[1]

    def put(self, key: str | None, answer: Any) -> None:
        if key is None:
            return
        with self._lock:
            if key not in self._entries and len(self._entries) >= self._max:
                del self._entries[next(iter(self._entries))]  # oldest insertion
            self._entries[key] = (self._clock(), answer)


# Catalog/prescription names carry the packaging ("Amlodipine Stada 5mg TAB
# 10x14"); patient-facing labels only need the product and strength. Display
# only -- ids, tool calls and evidence always keep the full name.
_PACKAGING_TAIL = re.compile(
    r"\s+(?:\(?(?:tab|tabs|cap|caps|viên|vien|hộp|hop|vỉ|chai|lọ|gói|goi)\b|\(?\d+\s*[x×]\s*\d+).*$",
    re.IGNORECASE,
)


def short_drug_name(name: str) -> str:
    return _PACKAGING_TAIL.sub("", name).strip() or name
