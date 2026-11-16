"""Per-brand deck behaviour: commodity presentation and optional slide texts.

``BrandPolicy`` is the single object that answers "how does this brand's deck differ?".
It is resolved once per deck (in the plan Lambda) and carried in the request snapshot,
so plan and render always agree and the render Lambda needs no extra DB round trip.

A brand without rows in ``T_Control_Autoreport_BrandCommodities`` /
``T_Control_Autoreport_BrandFeatures`` keeps the default behaviour: all commodities as
the source returns them, and no optional texts.
"""

from __future__ import annotations

import dataclasses
import logging

import pandas as pd

from pptcreator.kpi.commodity_policy import CommodityPolicy, load_commodity_policy
from pptcreator.kpi.control_tables import read_control_table_safe
from pptcreator.models.models import AutoreportBrandFeatures, AutoreportBrands

FEATURE_FOOTNOTE_TEXT = "footnote_text"
"""Text of the template's ``{footnote}`` token; no row -> empty (shape stays blank)."""

SUPPORTED_FEATURES = (FEATURE_FOOTNOTE_TEXT,)


@dataclasses.dataclass(frozen=True)
class BrandPolicy:
    """Everything the renderer needs to know about a brand's presentation."""

    brand: str = ""
    commodities: CommodityPolicy | None = None
    """None -> default commodity behaviour (all COMs, source labels/order)."""

    features: dict[str, str] = dataclasses.field(default_factory=dict)
    """feature_key -> value; missing key -> the feature is off."""

    def feature(self, key: str, default: str = "") -> str:
        return self.features.get(key, default)

    @property
    def footnote_text(self) -> str:
        return self.feature(FEATURE_FOOTNOTE_TEXT)

    def to_event(self) -> dict:
        return {
            "brand": self.brand,
            "commodities": self.commodities.to_event() if self.commodities else None,
            "features": dict(self.features),
        }

    @classmethod
    def from_event(cls, event: dict | None) -> BrandPolicy:
        """Rebuild the snapshot; tolerant of older/partial payloads."""
        if not event:
            return cls()
        commodities = event.get("commodities") or None
        return cls(
            brand=str(event.get("brand") or ""),
            commodities=CommodityPolicy.from_event(commodities),
            features={str(k): str(v) for k, v in (event.get("features") or {}).items()},
        )


def load_brand_policy(brand: str, engine=None) -> BrandPolicy:
    """Resolve the policy of one brand (``T_Control_Autoreport_Brands.filter_value``)."""
    brand = (brand or "").strip()
    if not brand:
        return BrandPolicy()

    features = _load_features(brand, engine)
    unknown = sorted(set(features) - set(SUPPORTED_FEATURES))
    if unknown:
        logging.warning(
            f"Brand {brand!r}: ignoring unsupported feature key(s) {unknown}."
        )

    policy = BrandPolicy(
        brand=brand,
        commodities=load_commodity_policy(brand, engine),
        features={k: v for k, v in features.items() if k in SUPPORTED_FEATURES},
    )
    logging.info(
        f"Brand policy for {brand!r}: "
        f"commodities={'default' if policy.commodities is None else len(policy.commodities.entries)}, "
        f"features={sorted(policy.features)}"
    )
    return policy


def _load_features(brand: str, engine=None) -> dict[str, str]:
    rows = read_control_table_safe(AutoreportBrands, ["filter_value"], [brand], engine)
    if rows is None or rows.empty:
        return {}
    brand_id = int(rows.iloc[0]["id"])

    features = read_control_table_safe(
        AutoreportBrandFeatures, ["brand_id", "is_active"], [brand_id, True], engine
    )
    if features is None or features.empty:
        return {}

    result: dict[str, str] = {}
    for row in features.to_dict("records"):
        key = _text(row.get("feature_key"))
        if not key:
            continue
        # NULL/empty is a valid value (it switches the feature off explicitly)
        result[key] = (
            "" if _is_null(row.get("feature_value")) else str(row["feature_value"])
        )
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
