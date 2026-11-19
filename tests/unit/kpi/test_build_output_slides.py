import dataclasses

import pytest
from pptx import Presentation
from pptx.util import Inches

from pptcreator.creator.create_ppt.create_text_fields import create_text_fields
from pptcreator.kpi.base import KpiDefinition, KpiResult, KpiSnapshot, ReportPeriod
from pptcreator.kpi.brand_policy import FEATURE_FOOTNOTE_TEXT, BrandPolicy
from pptcreator.kpi.kpi_metric import KpiMetric
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
    date_period = ReportPeriod.parse("2025-11-18")
    assert date_period.date.isoformat() == "2025-11-18"
    assert date_period.display == "KW47/2025"
    assert ReportPeriod.parse("KW37").date is None
    with pytest.raises(ValueError):
        ReportPeriod.parse("week 37")
    with pytest.raises(ValueError):
        ReportPeriod.parse("2025-13-40")


def test_structured_headlines_for_template_styles():
    slides = build_output_slides([_result(["BC"])], template_slots=TEMPLATE_SLOTS)
    overview = slides[0]["charts"]["Chart 1"]["headline_lines"]
    # line 1: week (template 'first' run = bold) + brand ('rest' run = regular)
    assert overview[0] == [("KW37", "first"), (" \u2013 Audi", "rest")]
    assert overview[1] == [("Ø 1 Jahr", "first")]
    detail = slides[1]["charts"]["Chart 3"]["headline_lines"]
    assert detail == [[("BC Ø 2 Monate", "first")], [("KW37: Ø 2 Monate", "first")]]


def test_overview_slide_maps_reference_and_current():
    slides = build_output_slides([_result(["BC"])], template_slots=TEMPLATE_SLOTS)
    overview = slides[0]
    assert overview["template_slide"] == OVERVIEW_SLIDE
    assert overview["title"] == "Titel"
    assert overview["charts"]["Chart 1"]["headline"] == "KW37 – Audi\nØ 1 Jahr"
    assert overview["charts"]["Chart 2"]["headline"] == "KW45 – Audi\nØ 1 Jahr"
    assert overview["charts"]["Chart 1"]["filters"]["role"] == "reference"
    assert overview["charts"]["Chart 2"]["filters"]["role"] == "current"


def test_detail_slide_pagination():
    commodities = [f"C{i}" for i in range(10)]
    slides = build_output_slides([_result(commodities)], template_slots=TEMPLATE_SLOTS)
    details = [s for s in slides if s["template_slide"] == DETAIL_SLIDE]
    assert len(details) == 2
    assert details[0]["title"] == "Titel (1/2)"
    assert details[1]["title"] == "Titel (2/2)"
    # balanced: 10 commodities -> 5 + 5
    assert list(details[0]["charts"]) == TEMPLATE_SLOTS[1][:5]
    assert list(details[1]["charts"]) == TEMPLATE_SLOTS[1][:5]
    assert details[1]["charts"]["Chart 3"]["filters"]["commodity"] == "C5"
    assert details[0]["charts"]["Chart 3"]["headline"] == "C0 Ø 2 Monate\nKW37: Ø 2 Monate"

    eight = build_output_slides([_result([f"C{i}" for i in range(8)])], template_slots=TEMPLATE_SLOTS)
    assert [len(s["charts"]) for s in eight if s["template_slide"] == DETAIL_SLIDE] == [4, 4]


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
    assert slides[0]["charts"]["Chart 2"]["headline"] == "KW45 – Audi"
    assert slides[1]["charts"]["Chart 3"]["headline"] == "BC 3\nKW37: 3"


def test_rows_are_in_palette_order():
    result = _result(["BC"])
    result.current.total_rows = [{"category": "b", "value": 2.0}, {"category": "a", "value": 1.0}]
    slides = build_output_slides([result], template_slots=TEMPLATE_SLOTS)
    assert [r["category"] for r in slides[0]["charts"]["Chart 2"]["rows"]] == ["a", "b"]


def test_footnote_text_comes_from_the_brand_policy():
    footnote = "Nur BC, BI, BM, BN, BX, CB und ZB."
    slides = build_output_slides(
        [_result(["BC"])],
        template_slots=TEMPLATE_SLOTS,
        brand_policy=BrandPolicy(brand="VW PKW", features={FEATURE_FOOTNOTE_TEXT: footnote}),
    )
    assert {s["text_values"]["footnote"] for s in slides} == {footnote}


def test_footnote_defaults_to_empty_string():
    """Without a policy the token must be blanked, never left as a literal '{footnote}'."""
    slides = build_output_slides([_result(["BC"])], template_slots=TEMPLATE_SLOTS)
    assert {s["text_values"]["footnote"] for s in slides} == {""}

    no_footnote = build_output_slides(
        [_result(["BC"])], template_slots=TEMPLATE_SLOTS, brand_policy=BrandPolicy(brand="Audi")
    )
    assert {s["text_values"]["footnote"] for s in no_footnote} == {""}


def test_datenquelle_run_comes_from_the_current_snapshot():
    result = _result(["BC"])
    result.current.run_label = "V01-B (46/2025)"
    values = build_output_slides([result], template_slots=TEMPLATE_SLOTS)[0]["text_values"]
    assert values["datenquelle_run"] == "V01-B (46/2025)"
    assert values["laufkennung"] == "V01-B"

    # sources without run information fall back to the week label
    fallback = build_output_slides([_result(["BC"])], template_slots=TEMPLATE_SLOTS)[0]["text_values"]
    assert fallback["datenquelle_run"] == "KW45"


@pytest.mark.parametrize(
    ("wording", "expected"),
    [
        ("alle BKAs mit roten Wochen", "alle BKAs mit roten Wochen"),
        ("alle BKAs mit UVB Fehlern", "alle BKAs mit UVB Fehlern"),
        ("", "alle BKAs"),
        (None, "alle BKAs"),
    ],
)
def test_data_source_wording_on_overview_and_all_detail_slides(wording, expected):
    result = _result([f"C{i}" for i in range(10)])
    if wording is not None:
        metric = KpiMetric(kpi_key="t", metric_type="count", showed_bkas=wording)
        result.definition = dataclasses.replace(result.definition, metric=metric)
    slides = build_output_slides([result], template_slots=TEMPLATE_SLOTS)
    assert len(slides) == 3

    prs = Presentation()
    template = prs.slides.add_slide(prs.slide_layouts[6])
    textbox = template.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(1))
    textbox.text = "Filterung auf Einkaufsorganisation {brand}, {showed_Bkas}, {datenquelle_run}"
    for output in slides:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        create_text_fields(slide, template, output["text_values"])
        assert slide.shapes[0].text == f"Filterung auf Einkaufsorganisation Audi, {expected}, KW45"


PERCENT = KpiMetric(kpi_key="t", metric_type="percent", numerator_columns=("Rot",), denominator_columns=("y",),
                    label="rot", explanation_text="Anteil rote BKAs")


def _metric_result(metric, current: dict, reference: dict, *, total="45 %", ref_total="40 %") -> KpiResult:
    def snapshot(period, values, text):
        return KpiSnapshot(
            period=ReportPeriod.parse(period),
            total_rows=_rows(),
            commodity_rows={c: _rows() for c in values},
            metric_text=text,
            commodity_metric_text={c: v for c, v in values.items() if v is not None},
        )

    definition = dataclasses.replace(KPI, metric=metric)
    return KpiResult(
        definition=definition, brand="Audi",
        current=snapshot("KW45", current, total), reference=snapshot("KW37", reference, ref_total),
    )


def test_metric_value_under_every_donut():
    result = _metric_result(PERCENT, {"BC": "50 %", "BI": None, "BM": "7 %"}, {"BC": "30 %", "BI": None})
    slides = build_output_slides([result], template_slots=TEMPLATE_SLOTS)

    # the star links the overview value to the explanation; detail slides have no explanation
    assert slides[0]["charts"]["Chart 1"]["headline"] == "KW37 – Audi\nrot 40 %*"
    assert slides[0]["charts"]["Chart 2"]["headline"] == "KW45 – Audi\nrot 45 %*"
    detail = slides[1]["charts"]
    assert detail["Chart 3"]["headline"] == "BC rot 50 %\nKW37: rot 30 %"
    # a COM without value (e.g. zero-filled) shows the empty text, a COM missing in the reference '-'
    assert detail["Chart 4"]["headline"] == "BI rot 0 %\nKW37: rot 0 %"
    assert detail["Chart 5"]["headline"] == "BM rot 7 %\nKW37: -"


def test_ratio_metric_without_label():
    ratio = KpiMetric(kpi_key="t", metric_type="ratio", denominator_columns=("RedOver52",))
    result = _metric_result(ratio, {"BC": "120 / 30"}, {"BC": "100 / 20"}, total="763 / 34", ref_total="700 / 30")
    slides = build_output_slides([result], template_slots=TEMPLATE_SLOTS)
    assert slides[0]["charts"]["Chart 2"]["headline"] == "KW45 – Audi\n763 / 34"  # no explanation -> no star
    assert slides[1]["charts"]["Chart 3"]["headline"] == "BC 120 / 30\nKW37: 100 / 20"


def test_avg_age_metric_renders_like_the_average_label():
    avg_age = KpiMetric(kpi_key="t", metric_type="avg_age", label="Ø")
    result = _metric_result(avg_age, {"BC": "2 Monate", "BI": None}, {"BC": "2 Monate", "BI": None}, total="1 Jahr", ref_total="1 Jahr")
    slides = build_output_slides([result], template_slots=TEMPLATE_SLOTS)
    assert slides[0]["charts"]["Chart 2"]["headline"] == "KW45 – Audi\nØ 1 Jahr"
    assert slides[1]["charts"]["Chart 3"]["headline"] == "BC Ø 2 Monate\nKW37: Ø 2 Monate"
    assert slides[1]["charts"]["Chart 4"]["headline"] == "BI 3\nKW37: 3"  # no average -> count, as before


def test_metric_not_computed_by_the_source_falls_back_to_the_average():
    result = _result(["BC"])
    result.definition = dataclasses.replace(KPI, metric=PERCENT)  # snapshot.metric_text is None
    slides = build_output_slides([result], template_slots=TEMPLATE_SLOTS)
    assert slides[0]["charts"]["Chart 2"]["headline"] == "KW45 – Audi\nØ 1 Jahr*"


def test_kpi_explanation_only_on_the_overview_slide():
    result = _metric_result(PERCENT, {"BC": "50 %"}, {"BC": "30 %"})
    slides = build_output_slides([result], template_slots=TEMPLATE_SLOTS)
    assert slides[0]["text_values"]["kpi_explanation"] == "* Anteil rote BKAs"
    assert slides[1]["text_values"]["kpi_explanation"] == ""

    without_metric = build_output_slides([_result(["BC"])], template_slots=TEMPLATE_SLOTS)
    assert {s["text_values"]["kpi_explanation"] for s in without_metric} == {""}


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
    assert [k.id for k in get_kpis(["uvb_fehlercode", "bka_aktualisierung"])] == ["uvb_fehlercode", "bka_aktualisierung"]
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
