"""Bang companion + companion_care_day (TASK-CAPY-13, ADR-0016).

Domain `companion` - Capybara Companion. Doc lap voi patient_reward_* (LP/SP):
khong bang nao o day tham gia diem thuong hay tuan thu lam sang. Xem
backend/db/models.py::Companion / CompanionCareDay va
backend/services/companion/service.py::tinh_lai_ngay.

Khong FK toi patient - cung convention voi patient_reward_account.

Revision ID: 0065
Revises: 0064
Create Date: 2026-11-14

"""

import sqlalchemy as sa
from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companion",
        sa.Column("patient_id", sa.String(), primary_key=True),
        sa.Column("celebrated_stage", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "companion_care_day",
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("care_date", sa.Date(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("patient_id", "care_date"),
        sa.CheckConstraint("units BETWEEN 0 AND 100", name="ck_companion_care_day_units"),
    )


def downgrade() -> None:
    op.drop_table("companion_care_day")
    op.drop_table("companion")
