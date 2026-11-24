"""End-to-end: the template's {footnote} shape only appears for a brand with a footnote.

Uses the real creation pipeline with the production template, so it also guards the
template contract: slide 2 carries a ``{footnote}`` text box, and a brand without a
footnote text must not get an empty text box copied onto its slides.
"""

import io
from pathlib import Path

from pptx import Presentation

from pptcreator.creator.create_ppt.graph_create_ppt import graph_create_ppt
from pptcreator.creator.get_config.get_template_config import get_template_config
from pptcreator.kpi.base import ReportPeriod
from pptcreator.kpi.brand_policy import FEATURE_FOOTNOTE_TEXT_DE, BrandPolicy
from pptcreator.kpi.build_output_slides import build_output_slides, discover_chart_slots
from pptcreator.kpi.commodity_policy import CommodityEntry, CommodityPolicy
from pptcreator.kpi.registry import get_kpis
from pptcreator.kpi.stub_source import StubKpiSource
from pptcreator.models.enum import Languages

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "test_data"
TEMPLATE_NAME = "VW_Template_Overview_DE.pptx"
FOOTNOTE_TEXT = "Darstellung auf sieben Commodities begrenzt."

VW_PKW_COMMODITIES = CommodityPolicy(
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


def _texts(slide) -> list[str]:
    return [s.text_frame.text for s in slide.shapes if s.has_text_frame]


def _render(storage, cont, brand: str, policy: BrandPolicy | None) -> Presentation:
    template_path = TEMPLATE_DIR / TEMPLATE_NAME
    storage.write_blob(
        container_name=cont,
        blob_name=TEMPLATE_NAME,
        blob_data=template_path.read_bytes(),
    )

    stub = StubKpiSource()
    results = [
        stub.fetch(
            definition, brand, ReportPeriod.parse("KW45"), ReportPeriod.parse("KW37")
        )
        for definition in get_kpis(["bka_aktualisierung"])
    ]
    if policy is not None and policy.commodities is not None:
        results = [policy.commodities.apply_to_result(result) for result in results]

    config = {
        "file": TEMPLATE_NAME,
        "file_container": cont,
        "target_file_name": f"footnote_{brand.replace(' ', '_')}",
        "target_blob_container": cont,
        "language": Languages.DE,
        "output_slides": build_output_slides(
            results,
            template_slots=discover_chart_slots(Presentation(template_path)),
            charts_per_detail_slide=7,
            brand_policy=policy,
        ),
    }
    config = get_template_config(config)
    graph_create_ppt(config)

    blob = storage.read_blob(
        container_name=cont,
        blob_name=f"{config['target_file_name']}.pptx",
        decode=False,
    )
    return Presentation(io.BytesIO(blob))


def test_template_has_the_footnote_token_on_the_detail_slide():
    prs = Presentation(TEMPLATE_DIR / TEMPLATE_NAME)
    assert any("{footnote}" in text for text in _texts(prs.slides[1]))


def test_vw_pkw_shows_the_footnote_on_the_detail_slide_only(storage, cont):
    prs = _render(
        storage,
        cont,
        "VW PKW",
        BrandPolicy(
            brand="VW PKW",
            commodities=VW_PKW_COMMODITIES,
            features={FEATURE_FOOTNOTE_TEXT_DE: FOOTNOTE_TEXT},
        ),
    )

    assert len(prs.slides) == 2
    overview, detail = prs.slides[0], prs.slides[1]
    assert not any(FOOTNOTE_TEXT in text for text in _texts(overview))
    assert FOOTNOTE_TEXT in _texts(detail)
    assert not any("{footnote}" in text for text in _texts(detail))


def test_other_brands_have_no_footnote_shape_at_all(storage, cont):
    prs = _render(storage, cont, "Audi", None)

    for slide in prs.slides:
        texts = _texts(slide)
        assert not any("{footnote}" in text for text in texts)
        assert not any(FOOTNOTE_TEXT in text for text in texts)


def test_empty_footnote_text_removes_the_shape(storage, cont):
    """An explicitly empty value must not leave an empty text box behind."""
    prs = _render(
        storage,
        cont,
        "SEAT",
        BrandPolicy(brand="SEAT", features={FEATURE_FOOTNOTE_TEXT_DE: ""}),
    )

    for slide in prs.slides:
        assert not any("{footnote}" in text for text in _texts(slide))
