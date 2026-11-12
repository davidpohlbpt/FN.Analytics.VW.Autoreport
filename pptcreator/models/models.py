import datetime as dt

import sqlalchemy as sa
from pycore.easy import DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column

from pptcreator.config import settings
from pptcreator.models.enum import Languages

SCHEMA = settings.app_db_schema


class Mappings(DeclarativeBase):
    __tablename__ = "T_CONTROL_PptCreator_Mappings"
    __table_args__ = {"schema": SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    """Internal identifier for mapping
    """

    template_object_name: Mapped[str] = mapped_column(sa.String(500))
    """Object identifier for object in the ppt templates
    """

    menu_item_id: Mapped[int]
    """Menu item id in DQN
    """

    report_id: Mapped[int]
    """Report Id in DQN
    """

    tile_id: Mapped[int]
    """Tile identifier in DQN
    """

    chart_id: Mapped[int]
    """Chart identifier in DQN
    """

    template_id: Mapped[int] = mapped_column(
        sa.ForeignKey(f"{SCHEMA}.T_CONTROL_PptCreator_Templates.id"),
    )
    """Template identifier
    """


class Templates(DeclarativeBase):
    __tablename__ = "T_CONTROL_PptCreator_Templates"
    __table_args__ = {"schema": SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    """Internal identifier for template
    """

    template_link: Mapped[str] = mapped_column(sa.String(500))
    """Link to the ppt template in Azure Blob Storage
    """

    language: Mapped[Languages] = mapped_column(
        sa.Enum(Languages, values_callable=lambda e: [m.value for m in e])
    )

    filter_column: Mapped[str | None] = mapped_column(sa.String(500))  # nullable=True!
    """Filter column for the project, if None then no filtering is applied
    """

    is_active: Mapped[bool]
    """Indicates whether the template is active
    """

    target_file_name: Mapped[str] = mapped_column(sa.String(500))
    """Target file name for the generated ppt
    """

    target_blob_container: Mapped[str] = mapped_column(sa.String(500))
    """Target blob container for the generated ppt
    """

    headline_substring: Mapped[str] = mapped_column(sa.String(500))
    """Substring displayed in the headline plus slide specific filter string
    """


class Recipients(DeclarativeBase):
    __tablename__ = "T_CONTROL_PptCreator_Recipients"
    __table_args__ = {"schema": SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    """Internal identifier for recipient
    """

    recipient_email: Mapped[str] = mapped_column(sa.String(500))
    """Email of the recipient
    """

    template_id: Mapped[int] = mapped_column(
        sa.ForeignKey(f"{SCHEMA}.T_CONTROL_PptCreator_Templates.id"),
    )
    """Template identifier
    """

    is_active: Mapped[bool]
    """Indicates whether the recipient is active
    """


# ------------------------------------------------------------------------------ #
# Autoreport control tables (ReportDB, schema settings.autoreport_schema)
#
#   T_Control_Autoreport_Templates   what a report is: template file, language, KPIs
#   T_Control_Autoreport_Mappings    one row per KPI of a template: where its data
#                                    comes from (frontend chart or backend query)
#   T_Control_Autoreport_Brands      master list of brands (frontend dropdown)
#   T_Control_Autoreport_Recipients  one row per deck a user wants: template, brand,
#                                    reference week (mandatory)
#   T_Control_Autoreport_Runs        audit log written by the Lambdas / state machine
# ------------------------------------------------------------------------------ #

AUTOREPORT_SCHEMA = settings.autoreport_schema


class AutoreportTemplates(DeclarativeBase):
    __tablename__ = "T_Control_Autoreport_Templates"
    __table_args__ = {"schema": AUTOREPORT_SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(sa.String(200))
    """Human readable name, e.g. 'VW KPI Weekly'"""

    template_link: Mapped[str] = mapped_column(sa.String(1000))
    """Location of the .pptx template: 's3://bucket/key' or 'container/file.pptx'"""

    language: Mapped[Languages] = mapped_column(
        sa.Enum(Languages, values_callable=lambda e: [m.value for m in e])
    )

    target_file_name: Mapped[str] = mapped_column(sa.String(500))
    """File name pattern; placeholders {brand} {current} {reference} are substituted"""

    target_location: Mapped[str | None] = mapped_column(sa.String(1000))
    """Where rendered decks go: 's3://bucket/prefix' or a storage container; None -> default"""

    commodity_charts_per_slide: Mapped[int | None] = mapped_column(default=None)
    """Detail charts per slide; None -> all chart slots found on the template slide"""

    email_subject: Mapped[str | None] = mapped_column(sa.String(500))
    """Subject pattern; placeholders {brand} {current} {reference}"""

    is_active: Mapped[bool] = mapped_column(default=True)


class AutoreportMappings(DeclarativeBase):
    """One row per KPI of a template. ``source`` decides where the numbers come from."""

    __tablename__ = "T_Control_Autoreport_Mappings"
    __table_args__ = {"schema": AUTOREPORT_SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    template_id: Mapped[int] = mapped_column(
        sa.ForeignKey(f"{AUTOREPORT_SCHEMA}.T_Control_Autoreport_Templates.id")
    )

    kpi_key: Mapped[str] = mapped_column(sa.String(100))
    """Stable KPI identifier, e.g. 'bka_age'; also the filter value in backend queries"""

    kpi_order: Mapped[int] = mapped_column(default=0)
    """Order of the KPI in the deck"""

    kpi_name: Mapped[str] = mapped_column(sa.String(200))
    """Short name used in headlines"""

    slide_title: Mapped[str] = mapped_column(sa.String(500))
    slide_subtitle: Mapped[str | None] = mapped_column(sa.String(1000))

    source: Mapped[str] = mapped_column(sa.String(20))
    """'frontend' (DQN chart API), 'backend' (SQL on the KPI table) or 'stub'"""

    # frontend source: DQN identifiers of the chart that holds the KPI
    menu_item_id: Mapped[int | None]
    report_id: Mapped[int | None]
    tile_id: Mapped[int | None]
    chart_id: Mapped[int | None]

    # backend source: which query of pptcreator/kpi/sql_source.py to run
    query_key: Mapped[str | None] = mapped_column(sa.String(100))

    palette_json: Mapped[str | None] = mapped_column(sa.String(2000))
    """JSON {category: 'rgb(r, g, b)'} in category order. None -> frontend colours"""

    average_label: Mapped[str | None] = mapped_column(sa.String(20), default="Ø")
    """Prefix for the average text in headlines; NULL/'' -> KPI has no average"""

    is_active: Mapped[bool] = mapped_column(default=True)


class AutoreportBrands(DeclarativeBase):
    """Master list of brands; feeds the frontend dropdown."""

    __tablename__ = "T_Control_Autoreport_Brands"
    __table_args__ = {"schema": AUTOREPORT_SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    brand_name: Mapped[str] = mapped_column(sa.String(200))
    """Display name in the frontend, e.g. 'Volkswagen PKW'"""

    filter_value: Mapped[str] = mapped_column(sa.String(200))
    """Exact value in the data (EK_ORG in T_RESULT_Leitstand_Overview), e.g. 'VW PKW'"""

    is_active: Mapped[bool] = mapped_column(default=True)


class AutoreportRecipients(DeclarativeBase):
    """One row per deck a user wants: template + brand + reference week.

    The same e-mail may appear several times for the same template and brand with
    different reference weeks; each row yields its own deck (identical ones are merged).
    """

    __tablename__ = "T_Control_Autoreport_Recipients"
    __table_args__ = (
        sa.UniqueConstraint(
            "email", "template_id", "brand_id", "reference_year", "reference_week",
            name="UQ_Autoreport_Recipients",
        ),
        sa.CheckConstraint("reference_week BETWEEN 1 AND 53", name="CK_Autoreport_Recipients_Week"),
        {"schema": AUTOREPORT_SCHEMA, "extend_existing": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    template_id: Mapped[int] = mapped_column(
        sa.ForeignKey(f"{AUTOREPORT_SCHEMA}.T_Control_Autoreport_Templates.id")
    )

    email: Mapped[str] = mapped_column(sa.String(500))

    brand_id: Mapped[int] = mapped_column(
        sa.ForeignKey(f"{AUTOREPORT_SCHEMA}.T_Control_Autoreport_Brands.id")
    )

    reference_year: Mapped[int]
    """ISO year of the reference week (mandatory)"""

    reference_week: Mapped[int]
    """ISO week 1-53 of the reference week (mandatory)"""

    send_now: Mapped[bool | None] = mapped_column(default=False)
    """Ad hoc request flag set by the frontend; cleared by the planner when picked up"""

    is_active: Mapped[bool | None] = mapped_column(default=True)

    last_edited_at: Mapped[dt.datetime | None] = mapped_column(sa.DateTime)


class AutoreportRuns(DeclarativeBase):
    """Audit log: one row per deck, written by the planner and updated by the steps."""

    __tablename__ = "T_Control_Autoreport_Runs"
    __table_args__ = {"schema": AUTOREPORT_SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(sa.String(100))
    """UUID shared by all decks of one planner invocation"""

    template_id: Mapped[int]
    brand: Mapped[str] = mapped_column(sa.String(200))
    current_period: Mapped[str] = mapped_column(sa.String(50))
    reference_period: Mapped[str] = mapped_column(sa.String(50))
    recipients: Mapped[str] = mapped_column(sa.String(4000))
    """Semicolon separated"""

    trigger: Mapped[str] = mapped_column(sa.String(20))
    """'scheduled' | 'adhoc' | 'manual'"""

    status: Mapped[str] = mapped_column(sa.String(20))
    """'queued' | 'rendered' | 'sent' | 'failed'"""

    s3_key: Mapped[str | None] = mapped_column(sa.String(1000))
    message_id: Mapped[str | None] = mapped_column(sa.String(200))
    error: Mapped[str | None] = mapped_column(sa.String(4000))

    created_at: Mapped[dt.datetime | None] = mapped_column(sa.DateTime)
    updated_at: Mapped[dt.datetime | None] = mapped_column(sa.DateTime)
