"""The KPIs of the deck, in slide order.

KPI 1 carries the real texts and palette from the VW template. KPIs 2-6 are
placeholders with distinct palettes so the deck structure can be rendered and
reviewed; replace name/title/subtitle/palette once the definitions are confirmed.
"""

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
        id="kpi1",
        name="BKA Alter",
        title="BKAs nach Aktualisierung",
        subtitle=(
            "Wann wurden BKAs das letzte Mal bearbeitet und wie ist das "
            "durchschnittliche BKA Alter?"
        ),
        palette=BKA_AGE_PALETTE,
    ),
    # TODO: replace placeholders below with the confirmed KPI 2-6 definitions
    KpiDefinition(
        id="kpi2",
        name="KPI 2",
        title="KPI 2 (Platzhalter)",
        subtitle="Platzhalter-Untertitel KPI 2",
        palette=_BLUE_PALETTE,
    ),
    KpiDefinition(
        id="kpi3",
        name="KPI 3",
        title="KPI 3 (Platzhalter)",
        subtitle="Platzhalter-Untertitel KPI 3",
        palette=_STATUS_PALETTE,
        average_label=None,
    ),
    KpiDefinition(
        id="kpi4",
        name="KPI 4",
        title="KPI 4 (Platzhalter)",
        subtitle="Platzhalter-Untertitel KPI 4",
        palette=BKA_AGE_PALETTE,
    ),
    KpiDefinition(
        id="kpi5",
        name="KPI 5",
        title="KPI 5 (Platzhalter)",
        subtitle="Platzhalter-Untertitel KPI 5",
        palette=_STATUS_PALETTE,
        average_label=None,
    ),
    KpiDefinition(
        id="kpi6",
        name="KPI 6",
        title="KPI 6 (Platzhalter)",
        subtitle="Platzhalter-Untertitel KPI 6",
        palette=_BLUE_PALETTE,
    ),
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
