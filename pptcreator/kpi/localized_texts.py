"""Non-German versions of the texts kept in shared control tables.

``T_Control_Autoreport_KpiMetrics`` (explanation, data source wording) and
``T_Control_Autoreport_BrandFeatures`` (footnote) hold one German text per KPI/brand for
all templates. For an English deck, ``T_Control_Autoreport_Texts`` provides the
translation; a missing row or a stage without the table keeps the German text (logged).
"""

from __future__ import annotations

import dataclasses
import logging

from pptcreator.kpi import i18n
from pptcreator.kpi.brand_policy import FEATURE_FOOTNOTE_TEXT, BrandPolicy
from pptcreator.kpi.kpi_metric import KpiMetric, _text
from pptcreator.models.enum import Languages
from pptcreator.models.models import AutoreportTexts
from pptcreator.utils.read_data import read_data

TEXT_KPI_EXPLANATION = "kpi_explanation"
TEXT_KPI_SHOWED_BKAS = "kpi_showed_bkas"
TEXT_BRAND_FOOTNOTE = "brand_footnote"

Texts = dict[tuple[str, str], str]
"""(text_type, text_key) -> text."""


def load_texts(language) -> Texts:
    """Active texts of ``language``; empty for DE (the base texts are German)."""
    language = i18n.as_language(language)
    if language == Languages.DE:
        return {}
    try:
        rows = read_data(AutoreportTexts, ["language", "is_active"], [language.value, True])
    except Exception as exc:  # stage without 003_autoreport_english.sql
        logging.warning(f"Could not read T_Control_Autoreport_Texts; {language} deck keeps German texts: {exc}")
        return {}
    if rows is None or rows.empty:
        logging.warning(f"No {language} texts in T_Control_Autoreport_Texts; German texts are used.")
        return {}
    texts: Texts = {}
    for row in rows.to_dict("records"):
        text_type, key = _text(row.get("text_type")), _text(row.get("text_key"))
        if text_type and key:
            texts[(text_type, key)] = _text(row.get("text_value")) or ""
    return texts


def localize_metrics(metrics: dict[str, KpiMetric], texts: Texts, language) -> dict[str, KpiMetric]:
    if i18n.as_language(language) == Languages.DE:
        return metrics
    return {
        key: dataclasses.replace(
            metric,
            explanation_text=_lookup(texts, TEXT_KPI_EXPLANATION, key, metric.explanation_text),
            showed_bkas=_lookup(texts, TEXT_KPI_SHOWED_BKAS, key, metric.showed_bkas),
        )
        for key, metric in metrics.items()
    }


def localize_brand_policy(policy: BrandPolicy, texts: Texts, language) -> BrandPolicy:
    if i18n.as_language(language) == Languages.DE or not policy.footnote_text:
        return policy
    footnote = _lookup(texts, TEXT_BRAND_FOOTNOTE, policy.brand, policy.footnote_text)
    return dataclasses.replace(policy, features={**policy.features, FEATURE_FOOTNOTE_TEXT: footnote})


def _lookup(texts: Texts, text_type: str, key: str, german: str) -> str:
    if not german:
        return german
    if (text_type, key) not in texts:
        logging.warning(f"No translation for {text_type} {key!r}; using the German text.")
        return german
    return texts[(text_type, key)]
