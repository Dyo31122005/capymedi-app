"""TASK-V2.6-001 B + C: the patient's own prescription as chatbot context, and
schedule questions filtered by part of day."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from backend.agents.v2.drug_evidence import prescribed_ids_for
from backend.agents.v2.orchestrator import (
    _build_prescription_reply,
    _build_schedule_reply,
    _requested_part_of_day,
    _symptom_drug_link,
    classify_intent,
)
from backend.agents.v2.runtime import ReadOnlyAgentRuntime
from backend.agents.v2.time_query_engine import TimeGranularity, TimeRange, TimeRelation
from tests.test_agent_v2_drug_evidence import _CatalogTools, _item, _search_plan, _tools, _WebGateway
from tests.test_agent_v2_orchestrator import _limits

_PRESCRIPTION = {
    "id": "rx-1",
    "status": "active",
    "note": "Tăng huyết áp",
    "start_date": "2026-11-14",
    "end_date": "2026-12-13",
    "medications": [
        {"legacy_drug_id": "amlodipine-stada-5mg-tab-10x14", "name": "Amlodipine Stada 5mg TAB 10x14", "dose": "1 viên/lần",
         "meal_timing": "Sau ăn", "reminder_times": ["08:00"], "doses_per_day": 1},
        {"legacy_drug_id": "metformin-500mg-stella-3x10", "name": "Metformin 500mg Stella 3x10", "dose": "1 viên/lần",
         "meal_timing": "Cùng bữa ăn", "reminder_times": ["08:00", "20:00"], "doses_per_day": 2},
    ],
}


# -- B: "đơn thuốc của tôi gồm những gì?" -------------------------------------


def test_prescription_reply_lists_every_drug_as_prescribed():
    reply = _build_prescription_reply([_PRESCRIPTION], today=date(2026, 11, 14))
    assert "gồm 2 thuốc" in reply and "đến 13/12/2026" in reply
    assert "**Amlodipine Stada 5mg**: 1 viên/lần, 1 lần/ngày lúc 08:00, sau ăn" in reply
    assert "**Metformin 500mg Stella**: 1 viên/lần, 2 lần/ngày lúc 08:00 và 20:00, cùng bữa ăn" in reply
    assert "TAB 10x14" not in reply  # packaging dropped from the display name
    assert "tái khám" not in reply


def test_prescription_ending_within_a_week_reminds_a_follow_up_visit():
    assert "Đơn còn 3 ngày nữa là hết" in _build_prescription_reply([_PRESCRIPTION], today=date(2026, 12, 11))


def test_prescription_reply_answers_a_named_drug_yes_or_no():
    assert _build_prescription_reply([_PRESCRIPTION], today=date(2026, 11, 14), asked="Metformin").startswith(
        "Có, đơn thuốc hiện tại của bạn có"
    )
    no = _build_prescription_reply([_PRESCRIPTION], today=date(2026, 11, 14), asked="Losartan")
    assert no.startswith("Đơn thuốc hiện tại của bạn không có Losartan")


def test_no_prescription_is_said_plainly():
    assert "chưa có đơn thuốc" in _build_prescription_reply([], today=date(2026, 11, 14))


@pytest.mark.parametrize("message", ["Đơn thuốc của tôi gồm những gì?", "đơn của tôi có Losartan không?"])
def test_prescription_questions_route_to_the_prescription(message):
    assert classify_intent(message).intent.value == "PRESCRIPTION_INFORMATION"


# -- B: the prescribed product's leaflet is read, and only it ------------------


def test_prescribed_ids_match_the_searched_ingredient():
    ids = [m["legacy_drug_id"] for m in _PRESCRIPTION["medications"]]
    assert prescribed_ids_for("Metformin", ids) == ["metformin-500mg-stella-3x10"]
    assert prescribed_ids_for("Losartan", ids) == []


def test_runtime_reads_the_prescribed_product_instead_of_the_catalog_top_hit():
    domain = _CatalogTools(
        [_item("metformin-1000mg-stella", "Metformin 1000mg Stella"), _item("metformin-500mg-stella-3x10", "Metformin 500mg Stella")],
        {"metformin-1000mg-stella": ["Tiêu chảy."], "metformin-500mg-stella-3x10": ["Buồn nôn."]},
    )
    gateway = _WebGateway(_search_plan("Metformin"))
    ReadOnlyAgentRuntime(gateway, limits=_limits(max_steps=6, max_tool_calls=6), web_search_enabled=False).run(
        message="Metformin tôi đang uống có tác dụng phụ gì?",
        actor_role="patient",
        tools=_tools(domain),
        lookup_query="Metformin tôi đang uống có tác dụng phụ gì?",
        preferred_drug_ids=("metformin-500mg-stella-3x10",),
    )
    leaflets = [call for call in domain.calls if call[0] == "get_drug_info"]
    assert leaflets == [("get_drug_info", "metformin-500mg-stella-3x10")]  # no second product mixed in


# -- B: a reported symptom listed in the patient's own drug's leaflet ----------


class _LeafletTools:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, name, arguments):
        from backend.agents.v2.tools import ToolResult

        return ToolResult(name=name, data={"legacy_drug_id": arguments["legacy_drug_id"], "results": self.rows.get(arguments["legacy_drug_id"], [])})


def test_symptom_in_the_leaflet_is_linked_to_the_patients_drug_with_its_frequency():
    tools = _LeafletTools({
        "amlodipine-stada-5mg-tab-10x14": [
            {"field": "tac_dung_phu", "content": "Thường gặp: Rối loạn hệ thần kinh: Đau đầu, chóng mặt. Ít gặp: ho."}
        ]
    })
    link = _symptom_drug_link("tôi uống thuốc rồi mà vẫn hơi chóng mặt", _PRESCRIPTION["medications"], tools)
    assert link is not None
    assert "Amlodipine Stada 5mg bạn đang dùng, chóng mặt là tác dụng phụ thường gặp" in link
    assert "đừng tự ngừng" in link


def test_no_link_when_the_leaflet_does_not_list_the_symptom():
    tools = _LeafletTools({"amlodipine-stada-5mg-tab-10x14": [{"field": "tac_dung_phu", "content": "Ho, phù chân."}]})
    assert _symptom_drug_link("tôi bị chóng mặt", _PRESCRIPTION["medications"], tools) is None


# -- C: part of day ------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "part"),
    [
        ("tối nay tôi uống thuốc gì", "tối"),
        ("toi nay uong thuoc gi", "tối"),
        ("sáng mai uống gì", "sáng"),
        ("buổi chiều uống thuốc nào", "chiều"),
        ("đêm nay uống thuốc gì", "tối"),
        ("hôm nay tôi uống thuốc gì", None),
        ("hom nay toi uong thuoc gi", None),  # unaccented "toi" = "tôi", not "tối"
    ],
)
def test_requested_part_of_day(message, part):
    assert _requested_part_of_day(message) == part


@pytest.mark.parametrize(
    ("message", "day"),
    [("sáng mai uống gì", date(2026, 11, 15)), ("tối mai uống thuốc gì", date(2026, 11, 15)), ("đêm nay uống thuốc gì", date(2026, 11, 14))],
)
def test_part_of_day_phrases_resolve_to_a_schedule_day(message, day):
    decision = classify_intent(message, now=datetime(2026, 11, 14, 3, 0, tzinfo=UTC))
    assert decision.time_range is not None and decision.time_range.start_date == day


@pytest.mark.parametrize("message", ["tôi quá mệt", "toi qua met"])
def test_toi_qua_without_diacritics_is_not_last_night(message):
    assert classify_intent(message).time_range is None


def _today_range() -> TimeRange:
    return TimeRange(
        start_datetime=datetime(2026, 11, 14, tzinfo=UTC), end_datetime=datetime(2026, 11, 14, 23, 59, tzinfo=UTC),
        timezone="Asia/Ho_Chi_Minh", granularity=TimeGranularity.DAY, relation=TimeRelation.PRESENT,
        is_past=False, is_future=False, label="hôm nay",
    )


def _dose(hour_utc: int, name: str) -> dict:
    return {"scheduled_at": f"2026-11-14T{hour_utc:02d}:00:00+00:00", "status": "PENDING", "expected_items": [{"ten_thuoc": name}]}


def test_tonight_lists_only_the_evening_doses():
    items = [_dose(1, "Amlodipine"), _dose(13, "Metformin")]  # 08:00 and 20:00 local
    reply = _build_schedule_reply(items, time_range=_today_range(), now=datetime(2026, 11, 14, 3, tzinfo=UTC), part_of_day="tối")
    assert reply.startswith("Tối nay (14/11)")
    assert "Metformin" in reply and "Amlodipine" not in reply


def test_a_part_of_day_without_doses_says_so_and_points_to_the_next_one():
    items = [_dose(13, "Metformin")]
    reply = _build_schedule_reply(items, time_range=_today_range(), now=datetime(2026, 11, 14, 3, tzinfo=UTC), part_of_day="trưa")
    assert reply == "Trưa nay (14/11) bạn không có cữ thuốc nào. Cữ gần nhất tiếp theo là lúc 20:00 nhé."
