"""Wording and number formats that the code itself writes onto the slides, per deck language.

Everything else is configured per language elsewhere: slide titles in the template's
``T_Control_Autoreport_Mappings`` rows, chart legend labels in ``Translation.dbo.Translation``
and explanation/footnote texts in the ``_de`` / ``_en`` columns and feature keys of
``T_Control_Autoreport_KpiMetrics`` and ``T_Control_Autoreport_BrandFeatures``.
"""

from __future__ import annotations

import re

from pptcreator.models.enum import Languages

_TEXTS: dict[str, dict[Languages, str]] = {
    "all_bkas": {Languages.DE: "alle BKAs", Languages.EN: "all BKAs"},
    "no_com": {Languages.DE: "ohne COM", Languages.EN: "without COM"},
    "year": {Languages.DE: "Jahr", Languages.EN: "year"},
    "years": {Languages.DE: "Jahre", Languages.EN: "years"},
    "month": {Languages.DE: "Monat", Languages.EN: "month"},
    "months": {Languages.DE: "Monate", Languages.EN: "months"},
}


def as_language(language: str | Languages | None) -> Languages:
    """``None``/'' -> DE (the language of the base texts); unknown codes raise."""
    if not language:
        return Languages.DE
    return Languages(str(getattr(language, "value", language)).strip().upper())


def text(key: str, language: str | Languages | None) -> str:
    return _TEXTS[key][as_language(language)]


def week_label(label: str, language: str | Languages | None) -> str:
    """'KW47/2025' -> 'CW47/2025' for English decks; other labels are unchanged."""
    if as_language(language) == Languages.EN:
        return re.sub(r"KW(?=\d)", "CW", label)
    return label


def format_number(value: float | None, language: str | Languages | None) -> str:
    """Thousands separator: '1.234' (DE) / '1,234' (EN)."""
    formatted = f"{float(value or 0):,.0f}"
    return formatted if as_language(language) == Languages.EN else formatted.replace(",", ".")


def format_age(days: float, language: str | Languages | None) -> str:
    """Average age in days -> '2 Jahre, 9 Monate' / '2 years, 9 months'."""
    months = int(round(float(days) / 30.4375))
    years, rest = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} {text('year' if years == 1 else 'years', language)}")
    if rest or not years:
        parts.append(f"{rest} {text('month' if rest == 1 else 'months', language)}")
    return ", ".join(parts)
