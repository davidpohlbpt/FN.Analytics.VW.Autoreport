"""CommodityPolicy is pure: whitelist, rename, order and zero-fill without any I/O."""

import pytest

from pptcreator.kpi.base import KpiDefinition, KpiResult, KpiSnapshot, ReportPeriod
from pptcreator.kpi.build_output_slides import DETAIL_SLIDE, build_output_slides
from pptcreator.kpi.commodity_policy import CommodityEntry, CommodityPolicy

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

VW_PKW = CommodityPolicy(
    entries=(
        CommodityEntry("BC", "BC", 10),
        CommodityEntry("BI", "BI", 20),
        CommodityEntry("BM", "BM", 30),
        CommodityEntry("BN", "BN", 40),
        CommodityEntry("BX", "BX", 50),
        CommodityEntry("BP", "CB", 60),
        CommodityEntry("BL", "ZB", 70),
    )
)


def _rows(a=1.0, b=2.0):
    return [{"category": "a", "value": a}, {"category": "b", "value": b}]


def _result(commodities, *, avg=True, zero=()):
    def snapshot(period):
        return KpiSnapshot(
            period=ReportPeriod.parse(period),
            total_rows=_rows(),
            commodity_rows={
                c: _rows(0.0, 0.0) if c in zero else _rows() for c in commodities
            },
            average_text="1 Jahr" if avg else None,
            commodity_average_text={c: "2 Monate" for c in commodities} if avg else {},
        )

    return KpiResult(
        definition=KPI,
        brand="VW PKW",
        current=snapshot("KW45"),
        reference=snapshot("KW37"),
    )


SOURCE_COMS = ["BA", "BC", "BI", "BL", "BM", "BN", "BP", "BX", "ohne Kapa Daten", "SO"]


def test_policy_keeps_configured_order_and_renames():
    applied = VW_PKW.apply(_result(SOURCE_COMS).current)
    assert list(applied.commodity_rows) == ["BC", "BI", "BM", "BN", "BX", "CB", "ZB"]


def test_policy_drops_unconfigured_commodities():
    applied = VW_PKW.apply(_result(SOURCE_COMS).current)
    shown = set(applied.commodity_rows)
    assert "BA" not in shown and "SO" not in shown and "ohne Kapa Daten" not in shown


def test_policy_renames_average_text_keys():
    applied = VW_PKW.apply(_result(SOURCE_COMS).current)
    assert set(applied.commodity_average_text) == set(applied.commodity_rows)
    assert applied.commodity_average_text["CB"] == "2 Monate"


def test_policy_zero_fills_a_commodity_with_no_rows():
    # ZB/BL and CB/BP are absent from the snapshot entirely
    applied = VW_PKW.apply(_result(["BC", "BI", "BM", "BN", "BX"]).current)
    assert list(applied.commodity_rows) == ["BC", "BI", "BM", "BN", "BX", "CB", "ZB"]
    assert applied.commodity_rows["CB"] == [
        {"category": "a", "value": 0.0},
        {"category": "b", "value": 0.0},
    ]
    # No average text for a commodity that has no data
    assert "CB" not in applied.commodity_average_text


def test_policy_keeps_explicit_zero_values():
    applied = VW_PKW.apply(_result(SOURCE_COMS, zero=["BP"]).current)
    assert applied.commodity_rows["CB"] == [
        {"category": "a", "value": 0.0},
        {"category": "b", "value": 0.0},
    ]


def test_show_if_zero_false_skips_zero_and_missing_commodities():
    policy = CommodityPolicy(
        entries=(
            CommodityEntry("BC", "BC", 10, show_if_zero=False),
            CommodityEntry("BP", "CB", 20, show_if_zero=False),
            CommodityEntry("BL", "ZB", 30, show_if_zero=False),
        )
    )
    # BC present but all zero -> dropped; BP/BL absent from the data -> dropped
    applied = policy.apply(_result(["BC", "BI"], zero=["BC"]).current)
    assert applied.commodity_rows == {}


def test_policy_does_not_mutate_its_input():
    result = _result(SOURCE_COMS)
    before = {key: list(rows) for key, rows in result.current.commodity_rows.items()}
    VW_PKW.apply_to_result(result)
    assert list(result.current.commodity_rows) == list(before)
    assert result.current.commodity_rows == before


def test_policy_rejects_duplicates():
    with pytest.raises(ValueError, match="Duplicate commodity labels"):
        CommodityPolicy(entries=(CommodityEntry("BC", "X"), CommodityEntry("BI", "X")))
    with pytest.raises(ValueError, match="Duplicate commodity sources"):
        CommodityPolicy(entries=(CommodityEntry("BC", "X"), CommodityEntry("BC", "Y")))


def test_zero_fill_falls_back_to_any_known_commodity_categories():
    """A KPI without total rows must still get a renderable zero row set."""
    result = _result(["HI"])
    result.current.total_rows = []
    result.current.commodity_rows = {"HI": _rows(0.0, 0.0)}

    applied = VW_PKW.apply(result.current)

    assert applied.commodity_rows["CB"] == [
        {"category": "a", "value": 0.0},
        {"category": "b", "value": 0.0},
    ]


def test_zero_fill_without_any_categories_raises_a_clear_error():
    result = _result([])
    result.current.total_rows = []
    result.current.commodity_rows = {}

    with pytest.raises(ValueError, match="categories are unknown"):
        VW_PKW.apply(result.current)


def test_seven_commodities_fit_one_detail_slide():
    slides = build_output_slides(
        [VW_PKW.apply_to_result(_result(SOURCE_COMS))],
        template_slots=TEMPLATE_SLOTS,
        brand_policy=None,
    )
    details = [s for s in slides if s["template_slide"] == DETAIL_SLIDE]
    assert len(details) == 1
    assert details[0]["title"] == "Titel"  # no '(1/2)' suffix
    assert list(details[0]["charts"]) == TEMPLATE_SLOTS[1]
    headlines = [c["headline"].split("\n")[0] for c in details[0]["charts"].values()]
    assert headlines[0].startswith("BC")
    assert headlines[5].startswith("CB")  # renamed BP
    assert headlines[6].startswith("ZB")  # renamed BL
