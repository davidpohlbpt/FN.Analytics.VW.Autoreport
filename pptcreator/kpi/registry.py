"""Reference KPI definitions.

In production the KPIs come from T_Control_Autoreport_Mappings (see
``get_autoreport_config``). This module keeps the same six definitions in code so
that unit tests and local runs without a database can seed the control tables, and
so that ``deployment/sql/002_seed_vw_weekly.sql`` has a single source of truth.
"""

import json

from pptcreator.kpi.base import KpiDefinition

BKA_AGE_PALETTE = {
    "< 1 Jahr": "rgb(146, 208, 80)",
    "1-2 Jahre": "rgb(197, 224, 180)",
    "2 - 4 Jahre": "rgb(255, 230, 153)",
    "4 - 6 Jahre": "rgb(244, 177, 131)",
    "> 6 Jahre": "rgb(255, 0, 0)",
    "ohne Daten": "rgb(127, 127, 127)",
}

_BLUE_PALETTE = {
    "< 1 Jahr": "rgb(0, 51, 102)",
    "1-2 Jahre": "rgb(0, 102, 178)",
    "2 - 4 Jahre": "rgb(102, 163, 224)",
    "4 - 6 Jahre": "rgb(178, 210, 240)",
    "> 6 Jahre": "rgb(230, 240, 250)",
    "ohne Daten": "rgb(127, 127, 127)",
}

_STATUS_PALETTE = {
    "erfüllt": "rgb(146, 208, 80)",
    "teilweise erfüllt": "rgb(255, 230, 153)",
    "nicht erfüllt": "rgb(255, 0, 0)",
    "ohne Daten": "rgb(127, 127, 127)",
}

KPIS: list[KpiDefinition] = [
    KpiDefinition(
        id="bka_age",
        name="BKA Alter",
        title="BKAs nach Aktualisierung",
        subtitle=(
            "Wann wurden BKAs das letzte Mal bearbeitet und wie ist das "
            "durchschnittliche BKA Alter?"
        ),
        palette=BKA_AGE_PALETTE,
        source="stub",
        query_key="default",
        order=1,
    ),
    # TODO: replace placeholders below with the confirmed KPI 2-6 definitions
    KpiDefinition(id="kpi2", name="KPI 2", title="KPI 2 (Platzhalter)", subtitle="Platzhalter-Untertitel KPI 2", palette=_BLUE_PALETTE, source="stub", query_key="default", order=2),
    KpiDefinition(id="kpi3", name="KPI 3", title="KPI 3 (Platzhalter)", subtitle="Platzhalter-Untertitel KPI 3", palette=_STATUS_PALETTE, average_label=None, source="stub", query_key="default", order=3),
    KpiDefinition(id="kpi4", name="KPI 4", title="KPI 4 (Platzhalter)", subtitle="Platzhalter-Untertitel KPI 4", palette=BKA_AGE_PALETTE, source="stub", query_key="default", order=4),
    KpiDefinition(id="kpi5", name="KPI 5", title="KPI 5 (Platzhalter)", subtitle="Platzhalter-Untertitel KPI 5", palette=_STATUS_PALETTE, average_label=None, source="stub", query_key="default", order=5),
    KpiDefinition(id="kpi6", name="KPI 6", title="KPI 6 (Platzhalter)", subtitle="Platzhalter-Untertitel KPI 6", palette=_BLUE_PALETTE, source="stub", query_key="default", order=6),
]

KPI_BY_ID: dict[str, KpiDefinition] = {kpi.id: kpi for kpi in KPIS}


def get_kpis(ids: list[str] | None = None) -> list[KpiDefinition]:
    """All KPIs in deck order, or the given subset (in the given order)."""
    if not ids:
        return list(KPIS)
    unknown = [i for i in ids if i not in KPI_BY_ID]
    if unknown:
        raise ValueError(f"Unknown KPI ids {unknown}; known: {list(KPI_BY_ID)}")
    return [KPI_BY_ID[i] for i in ids]


def as_mapping_rows(template_id: int, kpis: list[KpiDefinition] | None = None) -> list[dict]:
    """Rows for T_Control_Autoreport_Mappings, e.g. to seed a test database."""
    rows = []
    for index, kpi in enumerate(kpis or KPIS, start=1):
        rows.append(
            {
                "id": index,
                "template_id": template_id,
                "kpi_key": kpi.id,
                "kpi_order": kpi.order or index,
                "kpi_name": kpi.name,
                "slide_title": kpi.title,
                "slide_subtitle": kpi.subtitle,
                "source": kpi.source,
                "menu_item_id": kpi.menu_item_id,
                "report_id": kpi.report_id,
                "tile_id": kpi.tile_id,
                "chart_id": kpi.chart_id,
                "query_key": kpi.query_key,
                "palette_json": json.dumps(kpi.palette, ensure_ascii=False),
                "average_label": kpi.average_label,
                "is_active": True,
            }
        )
    return rows
