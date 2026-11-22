"""Schema cho companion-api (api-contracts.md §3b, ADR-0016). Tach file rieng
cung ly do voi reward_schemas.py. KHONG co truong don vi noi bo (growth/units)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CompanionState(BaseModel):
    """GET/PATCH /api/v1/companion/me. Khi enabled=False chi co enabled va
    unavailable_reason, cac truong con lai la None."""

    enabled: bool
    unavailable_reason: Literal["FEATURE_OFF", "RUNTIME_UNSUPPORTED"] | None = None
    stage: int | None = None
    stage_key: str | None = None
    stage_label: str | None = None
    next_stage_key: str | None = None
    next_stage_label: str | None = None
    is_max_stage: bool | None = None
    progress_pct: int | None = None
    name: str | None = None
    pending_celebration_stage: int | None = None


class CompanionRenameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)  # service chot lai 1-20 sau khi strip


class CompanionEventRequest(BaseModel):
    event: Literal["FEED_TAP", "FEED_AUTO", "FEED_SKIP", "SUPPORTIVE_SHOWN", "GROWTH_SEEN", "SHEET_OPEN"]
