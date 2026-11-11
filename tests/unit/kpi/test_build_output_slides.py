import pytest

from pptcreator.kpi.base import KpiDefinition, KpiResult, KpiSnapshot, ReportPeriod
from pptcreator.kpi.build_output_slides import (
    DETAIL_SLIDE,
    OVERVIEW_SLIDE,
    build_output_slides,
    validate_template_slots,
)
from pptcreator.kpi.registry import KPIS, get_kpis
from pptcreator.kpi.stub_source import StubKpiSource

TEMPLATE_SLOTS = {
    0: ["Chart 1", "Chart 2"],
    1: ["Chart 3", "Chart 4", "Chart 5", "Chart 6", "Chart 7", "Chart 8", "Chart 9"],
}

KPI = KpiDefinition(
    id="t",
    name="Test",
    title="Titel",
    subtitle="Untertitel",
    palette={"a": "rgb(1, 2, 3)", "b": "rgb(4, 5, 6)"},
)


def _rows(a=1.0, b=2.0):
    return [{"category": "a", "value": a}, {"category": "b", "value": b}]


def _result(commodities: list[str], avg: bool = True) -> KpiResult:
    def snapshot(period):
        return KpiSnapshot(
            period=ReportPeriod.parse(period),
            total_rows=_rows(),
            commodity_rows={c: _rows() for c in commodities},
            average_text="1 Jahr" if avg else None,
            commodity_average_text={c: "2 Monate" for c in commodities} if avg else {},
        )

    return KpiResult(definition=KPI, brand="Audi", current=snapshot("KW45"), reference=snapshot("KW37"))


def test_period_parsing():
    assert str(ReportPeriod.parse("kw5")) == "KW05"
    assert str(ReportPeriod.parse("2026-KW37")) == "2026-KW37"
    with pytest.raises(ValueError):
        ReportPeriod.parse("week 37")


def test_overview_slide_maps_reference_and_current():
    slides = build_output_slides([_result(["BC"])], template_slots=TEMPLATE_SLOTS)
    overview = slides[0]
    assert overview["template_slide"] == OVERVIEW_SLIDE
    assert overview["title"] == "Titel"
    assert overview["charts"]["Chart 1"]["headline"] == "KW37 - Audi\nØ 1 Jahr"
    assert overview["charts"]["Chart 2"]["headline"] == "KW45 - Audi\nØ 1 Jahr"
    assert overview["charts"]["Chart 1"]["filters"]["role"] == "reference"
    assert overview["charts"]["Chart 2"]["filters"]["role"] == "current"


def test_detail_slide_pagination():
    commodities = [f"C{i}" for i in range(10)]
    slides = build_output_slides([_result(commodities)], template_slots=TEMPLATE_SLOTS)
    details = [s for s in slides if s["template_slide"] == DETAIL_SLIDE]
    assert len(details) == 2
    assert details[0]["title"] == "Titel (1/2)"
    assert details[1]["title"] == "Titel (2/2)"
    assert list(details[0]["charts"]) == TEMPLATE_SLOTS[1]
    assert list(details[1]["charts"]) == ["Chart 3", "Chart 4", "Chart 5"]
    assert details[1]["charts"]["Chart 3"]["filters"]["commodity"] == "C7"
    assert details[0]["charts"]["Chart 3"]["headline"] == "C0 Ø 2 Monate\nKW37: Ø 2 Monate"


def test_detail_slide_without_pagination_keeps_plain_title():
    slides = build_output_slides([_result(["BC", "BI"])], template_slots=TEMPLATE_SLOTS)
    assert slides[1]["title"] == "Titel"
    assert len(slides) == 2


def test_charts_per_detail_slide_override():
    slides = build_output_slides(
        [_result(["BC", "BI", "BM"])], template_slots=TEMPLATE_SLOTS, charts_per_detail_slide=2
    )
    assert [len(s["charts"]) for s in slides] == [2, 2, 1]


def test_headline_without_average():
    slides = build_output_slides([_result(["BC"], avg=False)], template_slots=TEMPLATE_SLOTS)
    assert slides[0]["charts"]["Chart 2"]["headline"] == "KW45 - Audi"
    assert slides[1]["charts"]["Chart 3"]["headline"] == "BC - KW45\nKW37"


def test_rows_are_in_palette_order():
    result = _result(["BC"])
    result.current.total_rows = [{"category": "b", "value": 2.0}, {"category": "a", "value": 1.0}]
    slides = build_output_slides([result], template_slots=TEMPLATE_SLOTS)
    assert [r["category"] for r in slides[0]["charts"]["Chart 2"]["rows"]] == ["a", "b"]


def test_unknown_category_is_rejected():
    result = _result(["BC"])
    result.current.total_rows.append({"category": "zzz", "value": 1.0})
    with pytest.raises(ValueError, match="zzz"):
        build_output_slides([result], template_slots=TEMPLATE_SLOTS)


def test_template_slot_validation():
    with pytest.raises(ValueError, match="exactly two"):
        validate_template_slots({0: ["Chart 1"], 1: ["Chart 3"]})
    with pytest.raises(ValueError, match="at least one"):
        validate_template_slots({0: ["Chart 1", "Chart 2"], 1: []})


def test_registry():
    assert len(KPIS) == 6
    assert [k.id for k in get_kpis(["kpi3", "bka_age"])] == ["kpi3", "bka_age"]
    with pytest.raises(ValueError, match="Unknown KPI"):
        get_kpis(["nope"])


def test_stub_source_is_deterministic_and_valid():
    source = StubKpiSource()
    a = source.fetch(KPIS[0], "Audi", ReportPeriod.parse("KW45"), ReportPeriod.parse("KW37"))
    b = source.fetch(KPIS[0], "Audi", ReportPeriod.parse("KW45"), ReportPeriod.parse("KW37"))
    assert a == b
    assert len(a.current.commodity_rows) == 10  # Audi stub has >7 to exercise pagination
    total = sum(r["value"] for r in a.current.total_rows)
    parts = sum(r["value"] for rows in a.current.commodity_rows.values() for r in rows)
    assert total == parts
