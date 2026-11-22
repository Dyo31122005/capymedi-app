"""Them dose_event.first_reported_at (TASK-CAPY-06, ADR-0016, BR-8.5).

Thoi diem server ghi nhan LAN DAU lieu vao TAKEN/DELAYED/AWAITING_CAREGIVER.
Ghi mot lan, khong ghi de - xem backend/services/dose_lifecycle.py
::danh_dau_da_bao_cao. Dung de (1) phan biet bao cao tre voi bao cao dung ngay
cho ho so lam sang, (2) xet "cung ngay" cho Capybara Companion.

NULLABLE va KHONG backfill: du lieu cu khong suy ra duoc thoi diem bao cao
that (dose_event khong luu, xem docstring cua cot trong models.py). Them cot
nullable tren Postgres la thao tac chi sua catalog, khong ghi lai bang.

Index MOT PHAN (chi dong co gia tri) cho job doi soat companion (P1) quet
"lieu duoc bao cao gan day" ma khong phai quet ca bang.

Revision ID: 0064
Revises: 0063
Create Date: 2026-11-14

"""

import sqlalchemy as sa
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

_INDEX = "ix_dose_event_first_reported_at"


def upgrade() -> None:
    op.add_column(
        "dose_event",
        sa.Column("first_reported_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        _INDEX,
        "dose_event",
        ["first_reported_at"],
        postgresql_where=sa.text("first_reported_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="dose_event")
    op.drop_column("dose_event", "first_reported_at")
