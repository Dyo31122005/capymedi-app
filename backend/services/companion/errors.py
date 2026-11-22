"""Loi nghiep vu cua domain `companion` (ADR-0004 muc 4)."""

from __future__ import annotations

from backend.services.prescription.errors import VmecError


class GiaiDoanKhongHopLeError(VmecError):
    """Ack le lon len cho giai doan Capy chua dat toi."""

    ma_loi = "COMPANION_STAGE_NOT_REACHED"
    http_status = 422


class TenKhongHopLeError(VmecError):
    """Ten Capy ngoai 1-20 ky tu."""

    ma_loi = "COMPANION_NAME_INVALID"
    http_status = 422
