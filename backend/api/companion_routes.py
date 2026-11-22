"""companion-api (TASK-CAPY-19, api-contracts.md §3b, ADR-0016).

Chi role patient; patient_id lay tu JWT, khong nhan tu body/query - giong
reward_routes.py. GET la DOC THUAN. Cac route ghi tra 409 khi companion chua
bat cho benh nhan nay (co tat / ngoai cohort / runtime v2).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import status as http_status
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user
from backend.db.base import get_db
from backend.models.companion_schemas import CompanionEventRequest, CompanionRenameRequest, CompanionState
from backend.services.companion import service
from backend.services.prescription.errors import VmecError

companion_router = APIRouter()
logger = logging.getLogger("companion.events")


def _patient_id(current_user: CurrentUser) -> str:
    if current_user.role != "patient" or not current_user.patient_id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Chỉ bệnh nhân mới xem được Capy của chính mình",
        )
    return current_user.patient_id


def _yeu_cau_kha_dung(patient_id: str) -> None:
    if not service.companion_bat_cho(patient_id):
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="Capy chưa được bật cho tài khoản này")


@companion_router.get("/companion/me", response_model=CompanionState)
def get_my_companion(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CompanionState:
    return CompanionState(**service.lay_trang_thai(db, _patient_id(current_user)))


@companion_router.patch("/companion/me", response_model=CompanionState)
def rename_my_companion(
    body: CompanionRenameRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CompanionState:
    patient_id = _patient_id(current_user)
    _yeu_cau_kha_dung(patient_id)
    try:
        service.dat_ten(db, patient_id, body.name)
    except VmecError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.http_status, detail=exc.thong_bao) from exc
    db.commit()
    return CompanionState(**service.lay_trang_thai(db, patient_id))


@companion_router.post("/companion/me/celebrations/{stage}/ack", status_code=http_status.HTTP_204_NO_CONTENT)
def ack_celebration(
    stage: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    patient_id = _patient_id(current_user)
    _yeu_cau_kha_dung(patient_id)
    try:
        service.xac_nhan_da_mung(db, patient_id, stage)
    except VmecError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.http_status, detail=exc.thong_bao) from exc
    db.commit()
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@companion_router.post("/companion/me/events", status_code=http_status.HTTP_202_ACCEPTED)
def record_event(
    body: CompanionEventRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    """Event do luong UI (pilot). Chi ghi log JSON - khong DB, khong PHI."""
    patient_id = _patient_id(current_user)
    logger.info(json.dumps({"event": f"companion_ui.{body.event}", "patient_id": patient_id}))
    return Response(status_code=http_status.HTTP_202_ACCEPTED)
