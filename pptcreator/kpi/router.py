"""Selects the KpiSource per KPI based on ``KpiDefinition.source``."""

from __future__ import annotations

import logging

from pptcreator.kpi.base import KpiDefinition, KpiResult, KpiSource, ReportPeriod


class RoutingKpiSource:
    """Delegates ``fetch`` to the source named in the definition (frontend/backend/stub).

    Sources are created lazily so that e.g. a deck with only backend KPIs never logs in
    to the DQN API.
    """

    def __init__(self, sources: dict[str, KpiSource] | None = None):
        self._sources: dict[str, KpiSource] = dict(sources or {})

    def source_for(self, name: str) -> KpiSource:
        if name not in self._sources:
            self._sources[name] = _create(name)
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


def _create(name: str) -> KpiSource:
    if name == "stub":
        from pptcreator.kpi.stub_source import StubKpiSource

        return StubKpiSource()
    if name == "backend":
        from pptcreator.kpi.sql_source import SqlKpiSource

        return SqlKpiSource()
    if name == "frontend":
        from pptcreator.kpi.frontend_source import FrontendKpiSource

        return FrontendKpiSource()
    raise ValueError(f"Unknown KPI source {name!r}; expected frontend, backend or stub.")
