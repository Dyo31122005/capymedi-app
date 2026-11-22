"""photo_verification.evidence - bang chung co cau truc cua pipeline anh (TASK-CAPY-27).

Cot JSON nullable, them moi (additive), khong backfill: dong cu de NULL va API
van suy duoc `verification.verification_result` tu `ket_qua`.

Revision ID: 0066
Revises: 0065
Create Date: 2026-11-14

"""

import sqlalchemy as sa
from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("photo_verification", sa.Column("evidence", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("photo_verification", "evidence")
