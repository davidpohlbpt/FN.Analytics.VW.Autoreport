"""Local preview: render a KPI deck from ReportDB into the repo, without AWS.

    python -m pptcreator.preview --brand "VW PKW" --current 2025-11-18 --reference previous

* Reads the six Control Center KPIs live from ReportDB (read-only; the connection
  string comes from LOCAL_SQLSERVER_CONN_STR in .env).
* KPI definitions come from ``pptcreator/kpi/registry.py`` -- the control tables
  (T_Control_Autoreport_*) are NOT needed.
* Template from tests/unit/test_data/VW_Template_Overview.pptx (or --template).
* Output: previews/<file>.pptx (gitignored), optionally PNG slides via PowerPoint.

``--current latest`` picks the newest AnalyseZeitpunkt, ``--reference previous`` the
snapshot directly before the current one. Explicit dates (2025-11-18) or weeks
(2025-KW47) work too.
"""

from __future__ import annotations

import argparse
import logging
import os
import pathlib
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "tests" / "unit" / "test_data" / "VW_Template_Overview.pptx"
DEFAULT_OUT = ROOT / "previews"


def _load_env(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip().upper(), value.strip().strip('"'))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--brand", required=True, help="EK_ORG value, e.g. 'VW PKW'")
    parser.add_argument("--current", default="latest", help="'latest', a date (2025-11-18) or a week (2025-KW47)")
    parser.add_argument("--reference", default="previous", help="'previous', a date or a week")
    parser.add_argument("--kpi", action="append", help="KPI key subset (repeatable)")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--png", action="store_true", help="Also export slides as PNG (needs PowerPoint)")
    args = parser.parse_args(argv)

    _load_env(ROOT / ".env")
    # pycore: in-memory resources; only our own engine talks to SQL Server
    os.environ["RESOURCE_TYPE"] = "MEMORY"
    os.environ.setdefault("APP_NAME", "VwAutoreport")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", force=True)

    import sqlalchemy as sa
    from pptx import Presentation
    from pycore.easy import storage

    from pptcreator.creator.create_ppt.graph_create_ppt import graph_create_ppt
    from pptcreator.creator.get_config.get_kpi_deck_config import safe_file_name
    from pptcreator.creator.get_config.get_template_config import get_template_config
    from pptcreator.kpi.base import ReportPeriod
    from pptcreator.kpi.build_output_slides import build_output_slides, discover_chart_slots
    from pptcreator.kpi.leitstand_source import LeitstandKpiSource
    from pptcreator.kpi.registry import get_kpis

    conn = os.environ.get("LOCAL_SQLSERVER_CONN_STR")
    if not conn:
        print("LOCAL_SQLSERVER_CONN_STR missing in .env", file=sys.stderr)
        return 2
    engine = sa.create_engine("mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(conn))
    source = LeitstandKpiSource(engine)

    current_date = source.latest_date() if args.current == "latest" else source.resolve_date(ReportPeriod.parse(args.current))
    if args.reference == "previous":
        reference_date = source.previous_date(current_date)
    else:
        reference_date = source.resolve_date(ReportPeriod.parse(args.reference))
    current, reference = ReportPeriod.parse(current_date), ReportPeriod.parse(reference_date)
    print(f"Brand {args.brand!r}: current {current_date} ({current.display}) vs. reference {reference_date} ({reference.display})")

    results = [source.fetch(kpi, args.brand, current, reference) for kpi in get_kpis(args.kpi)]

    template = pathlib.Path(args.template)
    container = "preview"
    if not storage.container_exists(container):
        storage.create_container(container)
    storage.write_blob(container_name=container, blob_name=template.name, blob_data=template.read_bytes())

    name = safe_file_name(f"IDM_Control_Center_{args.brand}_{current_date}_vs_{reference_date}")
    config = {
        "file": template.name,
        "file_container": container,
        "target_file_name": name,
        "target_blob_container": container,
        "language": "DE",
        "output_slides": build_output_slides(
            results, template_slots=discover_chart_slots(Presentation(str(template))), charts_per_detail_slide=7
        ),
    }
    config = get_template_config(config)
    graph_create_ppt(config)

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{name}.pptx"
    out.write_bytes(storage.read_blob(container_name=container, blob_name=f"{name}.pptx", decode=False))
    print(f"Saved {out} ({len(config['output_slides'])} slides)")

    if args.png:
        png_dir = export_png(out)
        print(f"PNG slides in {png_dir}")
    return 0


def export_png(pptx_path: pathlib.Path, width: int = 1600) -> pathlib.Path:
    """Export every slide as PNG through PowerPoint COM (Windows with Office only)."""
    import win32com.client  # type: ignore[import-not-found]

    target = pptx_path.with_suffix("")
    target.mkdir(exist_ok=True)
    app = win32com.client.DispatchEx("PowerPoint.Application")
    try:
        prs = app.Presentations.Open(str(pptx_path.resolve()), ReadOnly=True, WithWindow=False)
        try:
            height = int(width * prs.PageSetup.SlideHeight / prs.PageSetup.SlideWidth)
            for index in range(1, prs.Slides.Count + 1):
                prs.Slides(index).Export(str((target / f"slide_{index:02d}.png").resolve()), "PNG", width, height)
        finally:
            prs.Close()
    finally:
        app.Quit()
    return target


if __name__ == "__main__":
    raise SystemExit(main())
