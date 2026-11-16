"""Per-brand commodity presentation (whitelist, rename, order, zero-fill).

The KPI sources return whatever the data contains, keyed by the raw ``COM`` value. Some
brands want a fixed set of commodities only, under a different label, in a fixed order,
and a chart even when the commodity has no data — that is what a ``CommodityPolicy``
expresses. It is pure: it never reads or writes anything, so it can be applied to any
``KpiSnapshot`` regardless of the ``KpiSource`` that produced it.

``load_commodity_policy`` reads the DB and returns ``None`` when the brand has no rows,
which keeps every other brand on the default behaviour.
"""

from __future__ import annotations

import dataclasses
import logging

import pandas as pd

from pptcreator.kpi.base import KpiResult, KpiSnapshot, Rows
from pptcreator.kpi.control_tables import read_control_table_safe
from pptcreator.models.models import AutoreportBrandCommodities, AutoreportBrands


@dataclasses.dataclass(frozen=True)
class CommodityEntry:
    """One commodity of a brand: source value in the data, label on the slide."""

    source: str
    label: str
    order: int = 0
    show_if_zero: bool = True


@dataclasses.dataclass(frozen=True)
class CommodityPolicy:
    """Ordered commodity presentation of one brand."""

    entries: tuple[CommodityEntry, ...]

    def __post_init__(self) -> None:
        labels = [e.label for e in self.entries]
        if len(labels) != len(set(labels)):
            raise ValueError(f"Duplicate commodity labels in the policy: {labels}.")
        sources = [e.source for e in self.entries]
        if len(sources) != len(set(sources)):
            raise ValueError(f"Duplicate commodity sources in the policy: {sources}.")

    @property
    def labels(self) -> list[str]:
        return [e.label for e in self.entries]

    def to_event(self) -> dict:
        return {
            "entries": [
                {
                    "source": e.source,
                    "label": e.label,
                    "order": e.order,
                    "show_if_zero": e.show_if_zero,
                }
                for e in self.entries
            ]
        }

    @classmethod
    def from_event(cls, event: dict | None) -> CommodityPolicy | None:
        """Rebuild the snapshot; ``None``/empty -> default behaviour."""
        if not event or not event.get("entries"):
            return None
        return cls(
            entries=tuple(
                CommodityEntry(
                    source=str(e["source"]),
                    label=str(e["label"]),
                    order=int(e.get("order") or 0),
                    show_if_zero=bool(e.get("show_if_zero", True)),
                )
                for e in event["entries"]
            )
        )

    def apply_to_result(self, result: KpiResult) -> KpiResult:
        """Return a copy of ``result`` with the policy applied to both snapshots."""
        return dataclasses.replace(
            result,
            current=self.apply(result.current),
            reference=self.apply(result.reference),
        )

    def apply(self, snapshot: KpiSnapshot) -> KpiSnapshot:
        """Return a copy of ``snapshot`` restricted, renamed, reordered and zero-filled."""
        commodity_rows: dict[str, Rows] = {}
        commodity_average_text: dict[str, str] = {}
        for entry in self.entries:
            rows = snapshot.commodity_rows.get(entry.source)
            average = snapshot.commodity_average_text.get(entry.source)

            if rows is None:
                if not entry.show_if_zero:
                    continue
                rows = _zero_rows(_categories(snapshot))
            elif not entry.show_if_zero and not any(r["value"] for r in rows):
                continue

            commodity_rows[entry.label] = rows
            if average is not None:
                commodity_average_text[entry.label] = average

        return dataclasses.replace(
            snapshot,
            commodity_rows=commodity_rows,
            commodity_average_text=commodity_average_text,
        )


def _categories(snapshot: KpiSnapshot) -> list[str]:
    """Category names of the brand total, i.e. every slice of the KPI's chart."""
    return [str(list(row.values())[0]) for row in snapshot.total_rows]


def _zero_rows(categories: list[str]) -> Rows:
    return [{"category": category, "value": 0.0} for category in categories]


# ------------------------------------------------------------------------------ #
# Loading
# ------------------------------------------------------------------------------ #


def load_commodity_policy(brand: str, engine=None) -> CommodityPolicy | None:
    """Commodity policy of one brand (``T_Control_Autoreport_Brands.filter_value``).

    Returns ``None`` when the brand has no active rows, i.e. default behaviour.
    ``engine`` is only needed outside the Lambdas (e.g. the local preview).
    """
    brand_id = _brand_id(brand, engine)
    if brand_id is None:
        return None

    rows = read_control_table_safe(
        AutoreportBrandCommodities, ["brand_id", "is_active"], [brand_id, True], engine
    )
    if rows is None or rows.empty:
        return None

    entries = [
        CommodityEntry(
            source=str(row["com_source"]).strip(),
            label=str(row["com_label"]).strip(),
            order=int(row["sort_order"] or 0),
            show_if_zero=bool(row["show_if_zero"]),
        )
        for row in rows.to_dict("records")
        if _text(row["com_source"]) and _text(row["com_label"])
    ]
    if not entries:
        return None

    entries.sort(key=lambda e: (e.order, e.source))
    policy = CommodityPolicy(entries=tuple(entries))
    logging.info(
        f"Commodity policy for {brand!r}: {len(entries)} COMs "
        f"({', '.join(f'{e.source}->{e.label}' for e in entries)})"
    )
    return policy


def _brand_id(brand: str, engine=None) -> int | None:
    value = _text(brand)
    if not value:
        return None
    rows = read_control_table_safe(AutoreportBrands, ["filter_value"], [value], engine)
    if rows is None or rows.empty:
        return None
    return int(rows.iloc[0]["id"])


def _text(value) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None
