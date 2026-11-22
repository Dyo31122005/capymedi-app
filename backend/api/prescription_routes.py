"""
POST /api/v1/prescriptions và vòng đời phác đồ (api-contracts.md §2).

Tầng này CHỈ làm việc HTTP: đọc body, gọi service, map lỗi (ADR-0004 §1).
Không có quy tắc nghiệp vụ nào nằm ở đây — tất cả nằm trong
`backend/services/prescription/service.py`, đọc test được mà không cần dựng app.

`get_current_doctor_id` đọc `doctor_id` thẳng từ body, cùng mẫu với
`get_current_patient_id` trong security.py: chưa có auth-api thật, nên phải
tin body — nhưng chỉ tin nó Ở ĐÚNG MỘT CHỖ NÀY, để sau này thay bằng đọc JWT
chỉ cần sửa một hàm.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.security import (
    CurrentUser,
    get_current_user,
    kiem_tra_quyen_du_lieu_benh_nhan,
    require_internal_secret,
    require_role,
)
from backend.db.base import get_db
from backend.db.models import Prescription
from backend.models.schemas import (
    PrescriptionApproveResponse,
    PrescriptionCreateRequest,
    PrescriptionDecisionRequest,
    PrescriptionListResponse,
    PrescriptionOut,
    PrescriptionUpdateRequest,
)
from backend.services.audit import log_action, patient_label
from backend.services.prescription import (
    VmecError,
    dem_lieu,
    dung_phac_do,
    duyet_phac_do,
    lay_phac_do,
    liet_ke_phac_do,
    sua_phac_do,
    tao_phac_do,
    tu_choi_phac_do,
)

prescription_router = APIRouter()


def _ghi_nhat_ky(
    db: Session, actor: CurrentUser | None, action: str, presc: Prescription
) -> None:
    """Ghi 1 dong nhat ky thao tac cho trang "Lịch sử" cua bac si.

    `actor` doc tu JWT (require_role bac si/admin) chu KHONG tu
    `payload.doctor_id`: cac route trong file nay van gac bang X-Internal-
    Secret va nhan doctor_id tu body, ma FE hien gui hang so `demo-doctor-01`
    (frontend/src/lib/prescriptions.ts) - ghi gia tri do vao nhat ky thi moi
    bac si deu thay thao tac cua nhau. Khong co JWT thi log_action() bo qua,
    khong ghi dong nao.

    Commit rieng SAU khi service da commit thay doi chinh: neu ke don thanh
    cong ma ghi nhat ky loi thi don thuoc van con, chi thieu dong nhat ky -
    khong lam nguoc lai (mat don thuoc vi loi ghi nhat ky).
    """
    if log_action(db, actor, action, patient_label(db, presc.patient_id)) is not None:
        db.commit()


def get_current_doctor_id(
    payload: PrescriptionCreateRequest | PrescriptionDecisionRequest | PrescriptionUpdateRequest,
    actor: CurrentUser | None = None,
) -> str:
    """1 CHỖ NỐI DUY NHẤT để đọc doctor_id — xem docstring module.

    Audit 2026-11-14: FE luôn gửi hằng số `demo-doctor-01` trong body, nên mọi
    đơn thuốc đều ghi sai bác sĩ. Khi có JWT bác sĩ thật (actor.role=doctor, có
    doctor_id) thì DÙNG DANH TÍNH ĐÓ; chỉ rơi về body khi không có JWT bác sĩ
    (vd test/script nội bộ gọi bằng X-Internal-Secret).

    Không đọc `payload.doctor_id` thẳng ở nơi khác, kể cả trong chính file này.

    2026-11-14 (vá bảo mật): tạo/duyệt/từ chối/dừng/sửa phác đồ đều bắt buộc
    JWT bác sĩ/admin (`require_role`). Trước đó 4 route này chỉ gác bằng
    X-Internal-Secret - header do chính proxy Next tự gắn cho MỌI người gọi -
    nên bệnh nhân đăng nhập tự tạo + tự duyệt được phác đồ cho mình (vượt HITL).
    Admin không có doctor_id nên vẫn rơi về body.
    """
    if actor is not None and actor.role == "doctor" and actor.doctor_id:
        return actor.doctor_id
    return payload.doctor_id


def _to_out(presc: Prescription) -> PrescriptionOut:
    return PrescriptionOut(
        id=presc.id,
        patient_id=presc.patient_id,
        doctor_id=presc.doctor_id,
        status=presc.status,
        items=presc.items,
        note=presc.note,
        start_date=presc.start_date,
        duration_days=presc.duration_days,
        approved_by=presc.approved_by,
        approved_at=presc.approved_at.isoformat() if presc.approved_at else None,
    )


@prescription_router.post(
    "/prescriptions",
    response_model=PrescriptionOut,
    status_code=201,
    dependencies=[Depends(require_internal_secret)],
)
def create_prescription(
    payload: PrescriptionCreateRequest,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(require_role("doctor", "admin", "super_admin")),
) -> PrescriptionOut:
    try:
        presc = tao_phac_do(
            db,
            patient_id=payload.patient_id,
            doctor_id=get_current_doctor_id(payload, actor),
            items=[item.model_dump() for item in payload.items],
            note=payload.note,
            start_date=payload.start_date,
            duration_days=payload.duration_days,
        )
    except VmecError as exc:
        raise _http(exc) from exc
    _ghi_nhat_ky(db, actor, f"Tạo phác đồ mới ({len(payload.items)} thuốc)", presc)
    return _to_out(presc)


@prescription_router.get(
    "/prescriptions",
    response_model=PrescriptionListResponse,
    dependencies=[Depends(require_internal_secret)],
)
def list_prescriptions(
    patient_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PrescriptionListResponse:
    """Hàng đợi duyệt = gọi với `status=draft`.

    Audit 2026-11-14: trước đây không cần đăng nhập. Có `patient_id` -> phải có
    quyền với bệnh nhân đó; KHÔNG có (danh sách toàn hệ thống) -> chỉ bác sĩ/admin.
    """
    if patient_id:
        kiem_tra_quyen_du_lieu_benh_nhan(db, current_user, patient_id)
    elif current_user.role not in ("doctor", "admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Chỉ bác sĩ/quản trị xem được danh sách phác đồ.")
    items = liet_ke_phac_do(db, patient_id=patient_id, status=status)
    return PrescriptionListResponse(items=[_to_out(p) for p in items])


@prescription_router.get(
    "/prescriptions/{prescription_id}",
    response_model=PrescriptionOut,
    dependencies=[Depends(require_internal_secret)],
)
def get_prescription(
    prescription_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PrescriptionOut:
    try:
        presc = lay_phac_do(db, prescription_id)
    except VmecError as exc:
        raise _http(exc) from exc
    kiem_tra_quyen_du_lieu_benh_nhan(db, current_user, presc.patient_id)
    return _to_out(presc)


@prescription_router.put(
    "/prescriptions/{prescription_id}",
    response_model=PrescriptionOut,
    dependencies=[Depends(require_internal_secret)],
)
def update_prescription(
    prescription_id: str,
    payload: PrescriptionUpdateRequest,
    db: Session = Depends(get_db),
    # Audit 2026-11-14: trước đây AI CŨNG sửa được phác đồ qua proxy FE.
    _bac_si: CurrentUser = Depends(require_role("doctor", "admin", "super_admin")),
) -> PrescriptionOut:
    try:
        presc, _ = sua_phac_do(
            db,
            prescription_id,
            doctor_id=get_current_doctor_id(payload, _bac_si),
            items=[item.model_dump() for item in payload.items],
            note=payload.note,
        )
    except VmecError as exc:
        raise _http(exc) from exc
    return _to_out(presc)


@prescription_router.post(
    "/prescriptions/{prescription_id}/approve",
    response_model=PrescriptionApproveResponse,
    dependencies=[Depends(require_internal_secret)],
)
def approve_prescription(
    prescription_id: str,
    payload: PrescriptionDecisionRequest,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(require_role("doctor", "admin", "super_admin")),
) -> PrescriptionApproveResponse:
    try:
        presc, so_lieu = duyet_phac_do(db, prescription_id, doctor_id=get_current_doctor_id(payload, actor))
    except VmecError as exc:
        raise _http(exc) from exc
    _ghi_nhat_ky(db, actor, f"Duyệt phác đồ (tạo {so_lieu} lượt uống)", presc)
    return PrescriptionApproveResponse(
        id=presc.id,
        status=presc.status,
        approved_by=presc.approved_by or "",
        approved_at=presc.approved_at.isoformat() if presc.approved_at else "",
        dose_events_created=so_lieu,
    )


@prescription_router.post(
    "/prescriptions/{prescription_id}/reject",
    response_model=PrescriptionOut,
    dependencies=[Depends(require_internal_secret)],
)
def reject_prescription(
    prescription_id: str,
    payload: PrescriptionDecisionRequest,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(require_role("doctor", "admin", "super_admin")),
) -> PrescriptionOut:
    try:
        presc = tu_choi_phac_do(db, prescription_id, doctor_id=get_current_doctor_id(payload, actor))
    except VmecError as exc:
        raise _http(exc) from exc
    _ghi_nhat_ky(db, actor, "Từ chối phác đồ", presc)
    return _to_out(presc)


@prescription_router.post(
    "/prescriptions/{prescription_id}/stop",
    response_model=PrescriptionOut,
    dependencies=[Depends(require_internal_secret)],
)
def stop_prescription(
    prescription_id: str,
    payload: PrescriptionDecisionRequest,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(require_role("doctor", "admin", "super_admin")),
) -> PrescriptionOut:
    try:
        presc, _ = dung_phac_do(db, prescription_id, doctor_id=get_current_doctor_id(payload, actor))
    except VmecError as exc:
        raise _http(exc) from exc
    _ghi_nhat_ky(db, actor, "Dừng phác đồ", presc)
    return _to_out(presc)


@prescription_router.get(
    "/prescriptions/{prescription_id}/dose-count",
    dependencies=[Depends(require_internal_secret)],
)
def count_doses(
    prescription_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Tiện cho việc verify thủ công/test — không nằm trong contract chính thức."""
    presc = lay_phac_do(db, prescription_id)  # 404 nếu không tồn tại
    kiem_tra_quyen_du_lieu_benh_nhan(db, current_user, presc.patient_id)
    return {"prescription_id": prescription_id, "dose_events": dem_lieu(db, prescription_id)}


def _http(exc: VmecError) -> HTTPException:
    return HTTPException(status_code=exc.http_status, detail=exc.to_contract()["error"])
