"""Selects the KpiSource per KPI based on ``KpiDefinition.source``."""

from __future__ import annotations

import logging

from pptcreator.kpi.base import KpiDefinition, KpiResult, KpiSource, ReportPeriod


class RoutingKpiSource:
    """Delegates ``fetch`` to the source named in the definition (leitstand/frontend/backend/stub).

    Sources are created lazily so that e.g. a deck with only backend KPIs never logs in
    to the DQN API.
    """

    def __init__(self, sources: dict[str, KpiSource] | None = None, *, language: str = "DE"):
        self._sources: dict[str, KpiSource] = dict(sources or {})
        self.language = str(getattr(language, "value", language) or "DE").upper()
        """Language of chart labels and formatted values (the template's language)."""

    def source_for(self, name: str) -> KpiSource:
        if name not in self._sources:
            self._sources[name] = _create(name, self.language)
        return self._sources[name]

    def fetch(
        self,
        definition: KpiDefinition,
        brand: str,
        current: ReportPeriod,
        reference: ReportPeriod,
    ) -> KpiResult:
        source = self.source_for(definition.source)
        logging.info(f"{definition.id}: fetching from {definition.source} source")
        return source.fetch(definition, brand, current, reference)


def _create(name: str, language: str = "DE") -> KpiSource:
    if name == "stub":
        from pptcreator.kpi.stub_source import StubKpiSource

        return StubKpiSource()
    if name == "backend":
        from pptcreator.kpi.sql_source import SqlKpiSource

        return SqlKpiSource()
    if name == "frontend":
        from pptcreator.kpi.frontend_source import FrontendKpiSource

        return FrontendKpiSource(language=language)
    if name == "leitstand":
        from pptcreator.kpi.leitstand_source import LeitstandKpiSource

        return LeitstandKpiSource(language=language)
    raise ValueError(f"Unknown KPI source {name!r}; expected leitstand, frontend, backend or stub.")
