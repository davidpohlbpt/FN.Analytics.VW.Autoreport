"""The six IDM Control Center KPIs (ReportDB report/menu item 1200, "Leitstand").

In production the KPIs come from T_Control_Autoreport_Mappings (see
``get_autoreport_config``) and, for ``source = 'leitstand'``, labels/colours/order are
read live from the Control Center chart configuration. The palettes below are a
snapshot of that configuration (ReportDB, 2026-11) used to seed the mapping table and
for tests/local runs without a database.

Donut chart -> T_RESULT_Leitstand_Overview columns (legend order):
  12000  UpdatedPastYear, UpdatedPast1to2Years, UpdatedPast2To4Years,
         UpdatedPast4To6Years, UpdatedOver6Years, NoUpdateData
  12002  BearbSynchron, BearbÜberarbeitungBes, BearbÜberarbeitungLief, BearbÜberarbeitungPCP
  12004  U0, U1, U2, U3
  12006  Red0to10, Red11to52, RedOver52
  120013 Gruen, Gelb, Rot, Grau
  120017 Kap1, Kap2to5, Kap6to10, KapOver10, KapNoData
"""

import json

from pptcreator.kpi.base import KpiDefinition

CONTROL_CENTER_MENU_ITEM = 1200

AKTUALISIERUNG_PALETTE = {
    "< 1 Jahr": "rgb(85, 204, 62)",
    "1-2 Jahre": "rgb(82, 197, 172)",
    "2 - 4 Jahre": "rgb(211, 246, 34)",
    "4 - 6 Jahre": "rgb(184, 184, 0)",
    "> 6 Jahre": "rgb(247, 48, 33)",
    "ohne Daten": "rgb(193, 193, 193)",
}

BEARBEITUNGSSTATUS_PALETTE = {
    "BKA beidseitig bestätigt": "rgb(82, 197, 172)",
    "BKA in Überarbeitung durch Beschaffer": "rgb(230, 230, 12)",
    "BKA in Überarbeitung durch Lieferant": "rgb(244, 168, 47)",
    "BKA in Überarbeitung durch PCP": "rgb(68, 88, 108)",
}

UVB_PALETTE = {
    "UVB 0 - Keine gültige Bestellung für Bedarf = 0": "rgb(82, 197, 172)",
    "UVB 1 - Keine Bestellung vorhanden oder Bestellung fehlt": "rgb(184, 184, 0)",
    "UVB 2 - Keine gültige Bestellung": "rgb(72, 91, 111)",
    "UVB 3 - Quote nicht 80% / 100%": "rgb(193, 193, 193)",
}

ROTE_BKA_PALETTE = {
    "< 10 Wochen": "rgb(237, 154, 143)",
    "11-52 Wochen": "rgb(233, 89, 73)",
    "> 53 Wochen": "rgb(147, 40, 11)",
}

ABGLEICHSTATUS_PALETTE = {
    "Grün": "rgb(85, 204, 62)",
    "Gelb": "rgb(245, 208, 47)",
    "Rot": "rgb(233, 89, 73)",
    "Grau": "rgb(128, 128, 128)",
}

KAPAZITAET_PALETTE = {
    "1 Eintrag": "rgb(192, 0, 0)",
    "2-5 Einträge": "rgb(0, 140, 130)",
    "6-10 Einträge": "rgb(153, 209, 205)",
    "> 10 Einträge": "rgb(230, 115, 100)",
    "Keine Einträge": "rgb(128, 128, 128)",
}

# Backwards compatible name used by older tests
BKA_AGE_PALETTE = AKTUALISIERUNG_PALETTE


def _kpi(order, key, name, title, subtitle, palette, chart_id, tile_id, average_label=None) -> KpiDefinition:
    return KpiDefinition(
        id=key,
        name=name,
        title=title,
        subtitle=subtitle,
        palette=palette,
        average_label=average_label,
        source="leitstand",
        menu_item_id=CONTROL_CENTER_MENU_ITEM,
        report_id=CONTROL_CENTER_MENU_ITEM,
        tile_id=tile_id,
        chart_id=chart_id,
        order=order,
    )


KPIS: list[KpiDefinition] = [
    _kpi(1, "bka_aktualisierung", "BKA nach Aktualisierung", "BKA nach Aktualisierung",
         "Wann wurden BKAs das letzte Mal bearbeitet und wie ist das durchschnittliche BKA Alter?",
         AKTUALISIERUNG_PALETTE, chart_id=12000, tile_id=12000, average_label="Ø"),
    _kpi(2, "bka_bearbeitungsstatus", "BKA nach Bearbeitungsstatus", "BKA nach Bearbeitungsstatus",
         "In welchem Handlungsfeld befinden sich die BKAs aktuell?",
         BEARBEITUNGSSTATUS_PALETTE, chart_id=12002, tile_id=12002),
    _kpi(3, "uvb_fehlercode", "UVB Fehler nach Fehlercode", "UVB Fehler nach Fehlercode",
         "Welche UVB Fehler enthalten die BKAs?",
         UVB_PALETTE, chart_id=12004, tile_id=12004),
    _kpi(4, "rote_bka", "Rote BKAs", "Rote BKAs",
         "Wie lange übersteigt der Bedarf die Maximalkapazität?",
         ROTE_BKA_PALETTE, chart_id=12006, tile_id=12006),
    _kpi(5, "bka_abgleichstatus", "BKA nach Abgleichstatus", "BKA nach Abgleichstatus",
         "Wie ist die Versorgungssituation laut Bedarfs-Kapazitäts-Abgleich?",
         ABGLEICHSTATUS_PALETTE, chart_id=120013, tile_id=120013),
    _kpi(6, "kapazitaet_saisonalitaet", "Saisonalität von Kapazitäten", "Saisonalität von Kapazitäten",
         "Wie viele unterschiedliche Kapazitätseinträge haben die BKAs?",
         KAPAZITAET_PALETTE, chart_id=120017, tile_id=120017),
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


def as_mapping_rows(template_id: int, kpis: list[KpiDefinition] | None = None, *, source: str | None = None) -> list[dict]:
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
                "source": source or kpi.source,
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
