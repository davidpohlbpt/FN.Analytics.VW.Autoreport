"""brandPolicy

Per-brand deck presentation: commodity whitelist/rename/order and optional feature texts.

Revision ID: 4a9c2f1d7b30
Revises: 1cbef96afcf4
Create Date: 2026-11-16 16:20:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "4a9c2f1d7b30"
down_revision = "1cbef96afcf4"
branch_labels = None
depends_on = None

SCHEMA = "control"

VW_PKW_COMMODITIES = [
    ("BC", "BC", 10),
    ("BI", "BI", 20),
    ("BM", "BM", 30),
    ("BN", "BN", 40),
    ("BX", "BX", 50),
    ("BP", "CB", 60),  # renamed
    ("BL", "ZB", 70),  # renamed
]

VW_PKW_FOOTNOTE = "Darstellung auf die Commodities BC, BI, BM, BN, BX, CB und ZB begrenzt."


def upgrade() -> None:
    op.create_table(
        "T_Control_Autoreport_BrandCommodities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("com_source", sa.String(length=50), nullable=False),
        sa.Column("com_label", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("show_if_zero", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            [f"{SCHEMA}.T_Control_Autoreport_Brands.id"],
            name=op.f("fk_T_Control_Autoreport_BrandCommodities_brand_id_T_Control_Autoreport_Brands"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_T_Control_Autoreport_BrandCommodities")),
        sa.UniqueConstraint(
            "brand_id", "com_source", name="UQ_Autoreport_BrandCommodities"
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "T_Control_Autoreport_BrandFeatures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("feature_key", sa.String(length=50), nullable=False),
        sa.Column("feature_value", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            [f"{SCHEMA}.T_Control_Autoreport_Brands.id"],
            name=op.f("fk_T_Control_Autoreport_BrandFeatures_brand_id_T_Control_Autoreport_Brands"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_T_Control_Autoreport_BrandFeatures")),
        sa.UniqueConstraint(
            "brand_id", "feature_key", name="UQ_Autoreport_BrandFeatures"
        ),
        schema=SCHEMA,
    )

    # Seed VW PKW by filter_value, never by a literal id: the id differs per stage.
    op.execute(
        sa.text(
            """
            INSERT INTO control.T_Control_Autoreport_BrandCommodities
                (brand_id, com_source, com_label, sort_order, show_if_zero, is_active)
            SELECT b.id, v.com_source, v.com_label, v.sort_order, 1, 1
            FROM control.T_Control_Autoreport_Brands b
            CROSS JOIN (VALUES
                ('BC', 'BC', 10),
                ('BI', 'BI', 20),
                ('BM', 'BM', 30),
                ('BN', 'BN', 40),
                ('BX', 'BX', 50),
                ('BP', 'CB', 60),
                ('BL', 'ZB', 70)
            ) AS v(com_source, com_label, sort_order)
            WHERE b.filter_value = N'VW PKW'
              AND NOT EXISTS (
                  SELECT 1 FROM control.T_Control_Autoreport_BrandCommodities bc
                  WHERE bc.brand_id = b.id
              )
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO control.T_Control_Autoreport_BrandFeatures
                (brand_id, feature_key, feature_value, is_active)
            SELECT b.id, N'footnote_text', :footnote, 1
            FROM control.T_Control_Autoreport_Brands b
            WHERE b.filter_value = N'VW PKW'
              AND NOT EXISTS (
                  SELECT 1 FROM control.T_Control_Autoreport_BrandFeatures bf
                  WHERE bf.brand_id = b.id AND bf.feature_key = N'footnote_text'
              )
            """
        ).bindparams(footnote=VW_PKW_FOOTNOTE)
    )


def downgrade() -> None:
    op.drop_table("T_Control_Autoreport_BrandFeatures", schema=SCHEMA)
    op.drop_table("T_Control_Autoreport_BrandCommodities", schema=SCHEMA)
