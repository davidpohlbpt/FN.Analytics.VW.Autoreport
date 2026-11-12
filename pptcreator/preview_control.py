"""Local end-to-end run driven by the control tables (T_Control_Autoreport_*).

    python -m pptcreator.preview_control --brand Audi
    python -m pptcreator.preview_control --brand "VW PKW" --current 2025-11-28 --reference 2025-11-11

Unlike ``pptcreator.preview`` (hard-coded KPI registry) this uses the real pipeline:
``T_Control_Autoreport_Templates`` + ``Mappings`` -> KPI definitions and template file,
``Brands`` + ``Recipients`` -> one deck per (brand, reference week). Renders through
``render_deck`` and copies the .pptx into ``previews/``. S3 and e-mail are disabled by
``.env`` (``s3_enabled`` / ``mail_enabled`` = false), so nothing leaves the machine.

The reference week comes from the recipient row. If that week has no Control Center
snapshot, the snapshot before the current one is used and logged.
"""

from __future__ import annotations

import argparse
import logging
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "previews"


def _load_env(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"')
            # Keep both spellings: pycore reads pydantic fields case-insensitively,
            # but some helpers look up the uppercase name directly.
            os.environ.setdefault(key, value)
            os.environ.setdefault(key.upper(), value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--brand",
        help="Brand filter_value (EK_ORG), e.g. 'Audi'; default: all recipients",
    )
    parser.add_argument(
        "--template-id", type=int, help="default: the only active template"
    )
    parser.add_argument(
        "--current",
        default="latest",
        help="'latest', a date (2025-11-28) or a week (2025-KW48)",
    )
    parser.add_argument(
        "--reference",
        default="db",
        help="'db' (recipient week), 'previous', a date or a week",
    )
    parser.add_argument("--kpi", action="append", help="KPI key subset (repeatable)")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    _load_env(ROOT / ".env")
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(message)s", force=True
    )

    from pycore.easy import storage

    from pptcreator.config import settings
    from pptcreator.creator.get_config.get_autoreport_config import (
        RecipientGroup,
        get_template_config,
        group_recipients,
        read_recipients,
    )
    from pptcreator.kpi.base import ReportPeriod
    from pptcreator.kpi.leitstand_source import LeitstandKpiSource
    from pptcreator.kpi.router import RoutingKpiSource

    template = get_template_config(args.template_id)
    source = RoutingKpiSource()
    snapshots = LeitstandKpiSource()

    current_date = (
        snapshots.latest_date()
        if args.current == "latest"
        else snapshots.resolve_date(ReportPeriod.parse(args.current))
    )
    current = ReportPeriod.parse(current_date)
    previous = ReportPeriod.parse(snapshots.previous_date(current_date))

    groups = group_recipients(read_recipients(template.id), template.id)
    if args.brand:
        wanted = args.brand.strip().lower()
        groups = [g for g in groups if g.brand.strip().lower() == wanted]
        if not groups:
            # Render any brand, even without an (active) recipient row.
            groups = [RecipientGroup(template.id, args.brand, previous, [], [])]
            logging.info(
                f"No active recipient row for {args.brand!r}; rendering without recipients."
            )

    print(f"Template {template.id} '{template.name}' from {template.template}")
    print(
        f"Current period: {current_date} ({current.display}); {len(groups)} recipient group(s)"
    )

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0

    for group in groups:
        reference = _reference_period(
            args.reference, group, snapshots, current_date, previous
        )
        outcome = _run(group, template, current, reference, source, args.kpi)
        if (
            outcome.status == "failed"
            and args.reference == "db"
            and reference != previous
        ):
            # Seed/placeholder reference weeks frequently have no snapshot for a brand.
            logging.warning(
                f"{group.brand}: reference {reference} has no usable data, retrying with {previous}"
            )
            reference, outcome = previous, _run(
                group, template, current, previous, source, args.kpi
            )
        if outcome.status == "failed":
            failures += 1
            print(f"FAILED {group.brand} {current} vs. {reference}: {outcome.error}")
            continue

        target = out_dir / outcome.file_name
        data = storage.read_blob(
            container_name=settings.storage_container,
            blob_name=outcome.file_name,
            decode=False,
        )
        try:
            target.write_bytes(data)
        except PermissionError:
            # File is open in PowerPoint (or locked by OneDrive sync); keep a copy.
            stem, suffix = target.stem, target.suffix
            counter = 2
            while True:
                target = out_dir / f"{stem}_{counter}{suffix}"
                if not target.exists():
                    break
                counter += 1
            target.write_bytes(data)
            logging.warning(f"Original file is locked; wrote {target.name} instead.")
        print(
            f"{outcome.status.upper()} {group.brand} {current} vs. {reference} -> {target}"
        )

    return 1 if failures else 0


def _reference_period(reference, group, snapshots, current_date, previous):
    """Explicit period, the snapshot before the current one, or the recipient row's week."""
    from pptcreator.kpi.base import ReportPeriod

    if reference == "previous":
        return previous
    if reference != "db":
        return ReportPeriod.parse(reference)

    requested = group.reference_period
    try:
        resolved = snapshots.resolve_date(requested)
    except ValueError as exc:
        logging.warning(
            f"{group.brand}: reference {requested} has no data ({exc}); using {previous}"
        )
        return previous
    if resolved >= current_date or not _has_brand_data(
        snapshots, group.brand, resolved
    ):
        logging.warning(
            f"{group.brand}: no data for reference {requested}; using {previous}"
        )
        return previous
    return requested


def _has_brand_data(snapshots, brand: str, date) -> bool:
    """Cheap existence check: does the brand have rows in that snapshot at all?"""
    import sqlalchemy as sa

    from pptcreator.kpi.leitstand_source import MOD_ALL, OVERVIEW_TABLE

    sql = sa.text(
        f"SELECT TOP 1 1 FROM {OVERVIEW_TABLE} WHERE AnalyseZeitpunkt = :d AND MOD = :mod AND EK_ORG = :brand"
    )
    with snapshots.engine.connect() as con:
        return (
            con.execute(sql, {"d": date, "mod": MOD_ALL, "brand": brand}).first()
            is not None
        )


def _run(group, template, current, reference, source, kpi_ids):
    from pptcreator.creator.get_config.get_kpi_deck_config import ReportRequest
    from pptcreator.creator.graph_steer_creation_process import run_deck

    request = ReportRequest.create(
        brand=group.brand,
        current_period=current,
        reference_period=reference,
        recipients=group.emails,
        template_id=template.id,
        kpi_ids=kpi_ids or None,
        recipient_ids=group.recipient_ids,
        trigger="manual",
    )
    return run_deck(request, source, template)


if __name__ == "__main__":
    raise SystemExit(main())
