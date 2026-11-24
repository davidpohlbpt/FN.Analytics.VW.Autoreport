"""English decks: translated control-table texts and language-dependent formats."""

import pandas as pd

from pptcreator.kpi import i18n
from pptcreator.kpi.brand_policy import FEATURE_FOOTNOTE_TEXT, BrandPolicy
from pptcreator.kpi.kpi_metric import KpiMetric
from pptcreator.kpi.localized_texts import load_texts, localize_brand_policy, localize_metrics
from pptcreator.models.models import AutoreportTexts


def _text(id_, text_type, key, value, active=True):
    return {"id": id_, "language": "EN", "text_type": text_type, "text_key": key,
            "text_value": value, "is_active": active}


def test_english_texts_replace_the_german_ones(data_repo):
    data_repo.database.create_all_tables()
    data_repo.write_table(
        model=AutoreportTexts,
        df=pd.DataFrame([
            _text(1, "kpi_explanation", "rote_bka", "Number of red BKAs"),
            _text(2, "brand_footnote", "VW PKW", "Note: other COMs."),
            _text(3, "kpi_explanation", "uvb_fehlercode", "outdated", active=False),
        ]),
    )
    metrics = {
        "rote_bka": KpiMetric("rote_bka", "ratio", explanation_text="Anzahl rote BKAs",
                              showed_bkas="alle BKAs mit roten Wochen"),
        "uvb_fehlercode": KpiMetric("uvb_fehlercode", "percent", explanation_text="Anteil grauer BKAs"),
    }
    texts = load_texts("EN")

    english = localize_metrics(metrics, texts, "EN")

    assert english["rote_bka"].explanation_text == "Number of red BKAs"
    assert english["rote_bka"].showed_bkas == "alle BKAs mit roten Wochen"  # no translation -> German
    assert english["uvb_fehlercode"].explanation_text == "Anteil grauer BKAs"  # inactive row ignored
    policy = BrandPolicy(brand="VW PKW", features={FEATURE_FOOTNOTE_TEXT: "Hinweis: andere COMs."})
    assert localize_brand_policy(policy, texts, "EN").footnote_text == "Note: other COMs."
    assert localize_metrics(metrics, texts, "DE") is metrics


def test_missing_texts_table_keeps_german_texts(data_repo):
    data_repo.database.create_all_tables()
    with data_repo.database.engine.begin() as con:
        con.exec_driver_sql("DROP TABLE IF EXISTS control.T_Control_Autoreport_Texts")
    assert load_texts("EN") == {}


def test_language_dependent_formats():
    assert i18n.format_age(400, "EN") == "1 year, 1 month"
    assert i18n.format_age(400, "DE") == "1 Jahr, 1 Monat"
    assert KpiMetric("rote_bka", "ratio").format(1200, 30, language="EN") == "1,200 / 30"
    assert KpiMetric("rote_bka", "ratio").format(1200, 30) == "1.200 / 30"
    assert i18n.week_label("KW47/2025", "EN") == "CW47/2025"
