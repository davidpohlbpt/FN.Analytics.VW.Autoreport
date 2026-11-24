"""BrandPolicy: DB loading and the "no rows = defaults" fallback."""

import pandas as pd
import pytest

from pptcreator.kpi.brand_policy import (
    FEATURE_FOOTNOTE_TEXT_DE,
    FEATURE_FOOTNOTE_TEXT_EN,
    BrandPolicy,
    load_brand_policy,
)
from pptcreator.kpi.commodity_policy import load_commodity_policy
from pptcreator.models.models import (
    AutoreportBrandCommodities,
    AutoreportBrandFeatures,
    AutoreportBrands,
    AutoreportTemplates,
)
from tests.unit.autoreport_fixtures import AUDI, SEAT, seed_control_tables  # noqa: F401

VW_PKW_ID = 5


@pytest.fixture
def control_tables(seed_control_tables, data_repo):  # noqa: F811
    seed_control_tables("VW.pptx", recipients=False)
    data_repo.write_table(
        model=AutoreportBrands,
        df=pd.DataFrame(
            [
                {
                    "id": VW_PKW_ID,
                    "brand_name": "Volkswagen PKW",
                    "filter_value": "VW PKW",
                    "is_active": True,
                }
            ]
        ),
    )
    return data_repo


def _seed_vw_pkw_policy(
    data_repo, *, footnote="Nur sieben COMs.", show_if_zero=True, is_active=True
):
    data_repo.write_table(
        model=AutoreportBrandCommodities,
        df=pd.DataFrame(
            [
                {
                    "id": i,
                    "brand_id": VW_PKW_ID,
                    "com_source": source,
                    "com_label": label,
                    "sort_order": order,
                    "show_if_zero": show_if_zero,
                    "is_active": is_active,
                }
                for i, (source, label, order) in enumerate(
                    [
                        ("BC", "BC", 10),
                        ("BI", "BI", 20),
                        ("BM", "BM", 30),
                        ("BN", "BN", 40),
                        ("BX", "BX", 50),
                        ("BP", "CB", 60),
                        ("BL", "ZB", 70),
                    ],
                    start=1,
                )
            ]
        ),
    )
    data_repo.write_table(
        model=AutoreportBrandFeatures,
        df=pd.DataFrame(
            [
                {
                    "id": 1,
                    "brand_id": VW_PKW_ID,
                    "feature_key": FEATURE_FOOTNOTE_TEXT_DE,
                    "feature_value": footnote,
                    "is_active": True,
                }
            ]
        ),
    )


def test_vw_pkw_policy_from_control_tables(control_tables):  # noqa: F811
    _seed_vw_pkw_policy(control_tables)

    policy = load_brand_policy("VW PKW")

    assert policy.brand == "VW PKW"
    assert policy.commodities is not None
    assert [e.label for e in policy.commodities.entries] == [
        "BC",
        "BI",
        "BM",
        "BN",
        "BX",
        "CB",
        "ZB",
    ]
    assert [e.source for e in policy.commodities.entries] == [
        "BC",
        "BI",
        "BM",
        "BN",
        "BX",
        "BP",
        "BL",
    ]
    assert policy.footnote_text == "Nur sieben COMs."


def test_brand_without_rows_keeps_defaults(control_tables):  # noqa: F811
    _seed_vw_pkw_policy(control_tables)

    policy = load_brand_policy("Audi")

    assert policy.commodities is None
    assert policy.footnote_text == ""
    assert policy.features == {}


def test_unknown_brand_keeps_defaults(control_tables):  # noqa: F811
    policy = load_brand_policy("Does Not Exist")
    assert policy.commodities is None and policy.footnote_text == ""


def test_inactive_commodity_rows_mean_default_behaviour(control_tables):  # noqa: F811
    _seed_vw_pkw_policy(control_tables, is_active=False)
    assert load_commodity_policy("VW PKW") is None


def test_unsupported_feature_keys_are_ignored(control_tables):  # noqa: F811
    _seed_vw_pkw_policy(control_tables)
    control_tables.write_table(
        model=AutoreportBrandFeatures,
        df=pd.DataFrame(
            [
                {
                    "id": 2,
                    "brand_id": VW_PKW_ID,
                    "feature_key": "not_a_feature",
                    "feature_value": "x",
                    "is_active": True,
                }
            ]
        ),
    )

    policy = load_brand_policy("VW PKW")

    assert "not_a_feature" not in policy.features
    assert policy.footnote_text == "Nur sieben COMs."


def test_policy_survives_a_missing_table(control_tables):  # noqa: F811
    """A stage without the new tables must render, just without the brand quirks."""
    control_tables.database.create_all_tables()
    control_tables.write_table(model=AutoreportTemplates, df=pd.DataFrame([]))
    with control_tables.database.engine.begin() as con:
        con.exec_driver_sql(
            "DROP TABLE IF EXISTS control.T_Control_Autoreport_BrandCommodities"
        )
        con.exec_driver_sql(
            "DROP TABLE IF EXISTS control.T_Control_Autoreport_BrandFeatures"
        )

    policy = load_brand_policy("VW PKW")

    assert policy.commodities is None
    assert policy.footnote_text == ""


def test_footnote_is_empty_without_a_policy():
    assert BrandPolicy().footnote_text == ""


def test_english_deck_uses_the_english_footnote_and_falls_back_to_german(control_tables):  # noqa: F811
    _seed_vw_pkw_policy(control_tables)
    assert load_brand_policy("VW PKW", "EN").footnote_text == "Nur sieben COMs."  # no EN row yet

    control_tables.write_table(
        model=AutoreportBrandFeatures,
        df=pd.DataFrame([{"id": 2, "brand_id": VW_PKW_ID, "feature_key": FEATURE_FOOTNOTE_TEXT_EN,
                          "feature_value": "Only seven COMs.", "is_active": True}]),
    )

    assert load_brand_policy("VW PKW", "EN").footnote_text == "Only seven COMs."
    assert load_brand_policy("VW PKW").footnote_text == "Nur sieben COMs."


def test_brand_ids_are_stable_but_not_relied_on():
    """The seed resolves VW PKW by filter_value, so a different id must still work."""
    assert VW_PKW_ID not in (AUDI, SEAT)
