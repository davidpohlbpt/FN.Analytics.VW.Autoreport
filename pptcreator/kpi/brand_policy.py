"""Per-brand deck behaviour: commodity presentation and optional slide texts.

``BrandPolicy`` is the single object that answers "how does this brand's deck differ?".
It is read from the control tables per deck (one query per table, independent of the
number of KPIs).

A brand without rows in ``T_Control_Autoreport_BrandCommodities`` /
``T_Control_Autoreport_BrandFeatures`` keeps the default behaviour: all commodities as
the source returns them, and no optional texts.
"""

from __future__ import annotations

import dataclasses
import logging

import pandas as pd

from pptcreator.kpi.commodity_policy import CommodityPolicy, load_commodity_policy
from pptcreator.models.models import AutoreportBrandFeatures, AutoreportBrands
from pptcreator.utils.read_data import read_data

FEATURE_FOOTNOTE_TEXT = "footnote_text"
"""Text of the template's ``{footnote}`` token; no row -> empty (shape is dropped)."""

SUPPORTED_FEATURES = (FEATURE_FOOTNOTE_TEXT,)


@dataclasses.dataclass(frozen=True)
class BrandPolicy:
    """Everything the renderer needs to know about a brand's presentation."""

    brand: str = ""
    commodities: CommodityPolicy | None = None
    """None -> default commodity behaviour (all COMs, source labels/order)."""

    features: dict[str, str] = dataclasses.field(default_factory=dict)
    """feature_key -> value; missing key -> the feature is off."""

    @property
    def footnote_text(self) -> str:
        return self.features.get(FEATURE_FOOTNOTE_TEXT, "")


def load_brand_policy(brand: str) -> BrandPolicy:
    """Resolve the policy of one brand (``T_Control_Autoreport_Brands.filter_value``)."""
    brand = (brand or "").strip()
    if not brand:
        return BrandPolicy()

    features = _load_features(brand)
    unknown = sorted(set(features) - set(SUPPORTED_FEATURES))
    if unknown:
        logging.warning(
            f"Brand {brand!r}: ignoring unsupported feature key(s) {unknown}."
        )

    policy = BrandPolicy(
        brand=brand,
        commodities=load_commodity_policy(brand),
        features={k: v for k, v in features.items() if k in SUPPORTED_FEATURES},
    )
    logging.info(
        f"Brand policy for {brand!r}: "
        f"commodities={'default' if policy.commodities is None else len(policy.commodities.entries)}, "
        f"features={sorted(policy.features)}"
    )
    return policy


def _load_features(brand: str) -> dict[str, str]:
    try:
        rows = read_data(AutoreportBrands, ["filter_value"], [brand])
        if rows is None or rows.empty:
            return {}
        brand_id = int(rows.iloc[0]["id"])

        features = read_data(
            AutoreportBrandFeatures, ["brand_id", "is_active"], [brand_id, True]
        )
    except Exception as exc:  # missing table on a stage without 004_brand_policy.sql
        logging.warning(f"Could not read the brand features for {brand!r}: {exc}")
        return {}
    if features is None or features.empty:
        return {}

    result: dict[str, str] = {}
    for row in features.to_dict("records"):
        key = _text(row.get("feature_key"))
        if key:
            # An empty value is valid: it switches the feature explicitly off.
            value = row.get("feature_value")
            result[key] = "" if _is_null(value) else str(value)
    return result


def _is_null(value) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _text(value) -> str | None:
    if _is_null(value):
        return None
    text = str(value).strip()
    return text or None
