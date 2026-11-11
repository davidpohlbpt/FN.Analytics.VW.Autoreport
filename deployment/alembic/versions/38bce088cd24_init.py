"""init

Revision ID: 38bce088cd24
Revises:
Create Date: 2026-09-09 16:09:53.900953

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "38bce088cd24"
down_revision = None
branch_labels = None
depends_on = None

SCHEMATA = ["control"]


def upgrade():
    for schema in SCHEMATA:
        op.execute(f"CREATE SCHEMA {schema}")


def downgrade():
    for schema in SCHEMATA:
        op.execute(f"DROP SCHEMA {schema}")
