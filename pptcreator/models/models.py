import datetime as dt

import sqlalchemy as sa
from pycore.easy import DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column

from pptcreator.config import settings
from pptcreator.models.enum import Languages

# ------------------------------------------------------------------------------ #
# Autoreport control tables (ReportDB, schema settings.autoreport_schema)
#
#   T_Control_Autoreport_Templates   what a report is: template file, language, KPIs
#   T_Control_Autoreport_Mappings    one row per KPI of a template: where its data
#                                    comes from (frontend chart or backend query)
#   T_Control_Autoreport_Brands      master list of brands (frontend dropdown)
#   T_Control_Autoreport_Recipients  one row per deck a user wants: template, brand,
#                                    reference week (mandatory); the frontend sets the
#                                    language, a trigger resolves template_id from it
#   T_Control_Autoreport_Texts       non-German versions of KPI/brand texts
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
    """Deprecated: fallback only when T_Control_Autoreport_KpiMetrics has no row for the KPI.
    Prefix for the average text in headlines; NULL/'' -> KPI has no average"""

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


class AutoreportBrandCommodities(DeclarativeBase):
    """Commodity presentation per brand: which COMs, which labels, which order.

    A brand without active rows keeps the default behaviour (all COMs the source returns,
    source labels, source order, COMs with an all-zero distribution skipped). Rows turn the
    brand into an explicit whitelist: only ``com_source`` values are shown, renamed to
    ``com_label``, ordered by ``sort_order``, and zero-valued COMs are kept when
    ``show_if_zero`` is set.
    """

    __tablename__ = "T_Control_Autoreport_BrandCommodities"
    __table_args__ = {"schema": AUTOREPORT_SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    brand_id: Mapped[int] = mapped_column(
        sa.ForeignKey(f"{AUTOREPORT_SCHEMA}.T_Control_Autoreport_Brands.id")
    )

    com_source: Mapped[str] = mapped_column(sa.String(50))
    """Value in T_RESULT_Leitstand_Overview.COM, e.g. 'BP'"""

    com_label: Mapped[str] = mapped_column(sa.String(50))
    """Label shown in the chart headline, e.g. 'CB'"""

    sort_order: Mapped[int] = mapped_column(default=0)
    """Position on the detail slide (ascending)"""

    show_if_zero: Mapped[bool] = mapped_column(default=True)
    """Keep the chart when the COM has no data or only zeros"""

    is_active: Mapped[bool] = mapped_column(default=True)


class AutoreportBrandFeatures(DeclarativeBase):
    """Free-form per-brand switches, so a brand quirk needs no schema change.

    A brand without an active row for a key falls back to the feature's default (off).
    """

    __tablename__ = "T_Control_Autoreport_BrandFeatures"
    __table_args__ = {"schema": AUTOREPORT_SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    brand_id: Mapped[int] = mapped_column(
        sa.ForeignKey(f"{AUTOREPORT_SCHEMA}.T_Control_Autoreport_Brands.id")
    )

    feature_key: Mapped[str] = mapped_column(sa.String(50))
    """e.g. 'footnote_text'"""

    feature_value: Mapped[str] = mapped_column(sa.String(200))
    """Text/render value of the feature, e.g. the footnote sentence"""

    is_active: Mapped[bool] = mapped_column(default=True)


class AutoreportKpiMetrics(DeclarativeBase):
    """The value under each donut per KPI (same for all brands and templates).

    Structured on purpose (no SQL text): numerator / denominator are sums of columns of
    T_RESULT_Leitstand_Overview, filtered like the donut. See pptcreator/kpi/kpi_metric.py.
    A KPI without an active row falls back to Mappings.average_label.
    """

    __tablename__ = "T_Control_Autoreport_KpiMetrics"
    __table_args__ = {"schema": AUTOREPORT_SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    kpi_key: Mapped[str] = mapped_column(sa.String(100))
    """Same key as T_Control_Autoreport_Mappings.kpi_key, e.g. 'rote_bka'"""

    metric_type: Mapped[str] = mapped_column(sa.String(20))
    """'avg_age' | 'percent' | 'ratio' | 'count'"""

    numerator_columns: Mapped[str | None] = mapped_column(sa.String(500))
    """Comma-separated columns summed per row; NULL -> the donut total"""

    numerator_not_null_column: Mapped[str | None] = mapped_column(sa.String(100))
    """Only rows where this column IS NOT NULL count towards the numerator"""

    denominator_columns: Mapped[str | None] = mapped_column(sa.String(500))
    """Comma-separated columns summed per row; NULL -> the donut total"""

    label: Mapped[str | None] = mapped_column(sa.String(50))
    """Prefix in front of the value, e.g. 'Ø'; NULL/'' -> value only"""

    explanation_text: Mapped[str | None] = mapped_column(sa.String(500))
    """Text of the template's {kpi_explanation} token on overview and COM slides"""

    showed_bkas: Mapped[str | None] = mapped_column(sa.String(200))
    """Data source wording for the template's {showed_Bkas} token"""

    is_active: Mapped[bool] = mapped_column(default=True)


class AutoreportTexts(DeclarativeBase):
    """Translations of the German texts stored in other control tables, per language.

    The base columns (KpiMetrics.explanation_text / showed_bkas, BrandFeatures
    'footnote_text') are German; a DE deck never reads this table. A missing row keeps
    the German text (logged). See pptcreator/kpi/localized_texts.py.
    """

    __tablename__ = "T_Control_Autoreport_Texts"
    __table_args__ = {"schema": AUTOREPORT_SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    language: Mapped[str] = mapped_column(sa.String(2))
    """'EN'"""

    text_type: Mapped[str] = mapped_column(sa.String(50))
    """'kpi_explanation' | 'kpi_showed_bkas' (text_key = kpi_key) or
    'brand_footnote' (text_key = Brands.filter_value)"""

    text_key: Mapped[str] = mapped_column(sa.String(200))

    text_value: Mapped[str] = mapped_column(sa.String(1000))

    is_active: Mapped[bool] = mapped_column(default=True)


class AutoreportRecipients(DeclarativeBase):
    """One row per deck a user wants: template + brand + two Control Center runs.

    The frontend maintains this table; the ``send_now`` flag is the only trigger of a
    deck. The weeks are the frontend dropdown strings (``V01-B (46/2025)`` =
    ``LAUFKENNUNG (LAUF_KW)``, see dbo.V_Autoreport_DropdownValues); dates
    (``YYYY-MM-DD``) and ``2025-KW46`` are accepted as well. They are passed through to
    the KPI source, which resolves the snapshot.
    """

    __tablename__ = "T_Control_Autoreport_Recipients"
    __table_args__ = {"schema": AUTOREPORT_SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    template_id: Mapped[int] = mapped_column(
        sa.ForeignKey(f"{AUTOREPORT_SCHEMA}.T_Control_Autoreport_Templates.id")
    )

    email: Mapped[str] = mapped_column(sa.String(1000))

    brand_id: Mapped[int] = mapped_column(
        sa.ForeignKey(f"{AUTOREPORT_SCHEMA}.T_Control_Autoreport_Brands.id")
    )

    report_week: Mapped[str] = mapped_column(sa.String(50))
    """Current run, e.g. 'V01-D (48/2025)', mandatory"""

    comparison_week: Mapped[str] = mapped_column(sa.String(50))
    """Comparison run, e.g. 'V01-B (46/2025)', mandatory"""

    send_now: Mapped[bool | None] = mapped_column(default=False)
    """Set by the frontend; reset by vw-autoreport-sendemail after sending, and on failure"""

    IsDeleted: Mapped[bool] = mapped_column(default=False)
    """Soft delete of the frontend; deleted rows are never planned"""


class AutoreportRuns(DeclarativeBase):
    """Audit log: one row per deck, written by the planner and updated by the steps."""

    __tablename__ = "T_Control_Autoreport_Runs"
    __table_args__ = {"schema": AUTOREPORT_SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(sa.String(100))
    """UUID shared by all decks of one planner invocation"""

    template_id: Mapped[int]
    recipients: Mapped[str | None] = mapped_column(sa.String(1000))
    """Email snapshot of the requesting recipient row (one recipient per deck)"""
    recipient_id: Mapped[int | None]
    """Row id in T_Control_Autoreport_Recipients; also the claim that prevents double sends"""

    brand: Mapped[str] = mapped_column(sa.String(200))
    current_period: Mapped[str | None] = mapped_column(sa.String(50))
    """Requested report_week"""
    reference_period: Mapped[str | None] = mapped_column(sa.String(50))
    """Requested comparison_week"""

    status: Mapped[str] = mapped_column(sa.String(20))
    """'processing' (claim) | 'rendered' | 'sent' | 'skipped' | 'failed'"""

    error: Mapped[str | None] = mapped_column(sa.String(4000))

    created_at: Mapped[dt.datetime | None] = mapped_column(sa.DateTime)
    updated_at: Mapped[dt.datetime | None] = mapped_column(sa.DateTime)
