"""KpiMetric: formatting, validation and loading from T_Control_Autoreport_KpiMetrics."""

import dataclasses
import json

import pandas as pd
import pytest

from pptcreator.creator.get_config.get_autoreport_config import _kpi_from_event
from pptcreator.kpi.kpi_metric import (
    KpiMetric,
    attach_metrics,
    format_percent,
    format_ratio,
    load_kpi_metrics,
)
from pptcreator.kpi.registry import KPIS
from pptcreator.models.models import AutoreportKpiMetrics


def test_percent_is_a_whole_number_rounded_half_up():
    assert format_percent(18, 40) == "45 %"
    assert format_percent(89, 200) == "45 %"  # 44.5 -> 45
    assert format_percent(1, 250) == "0 %"  # 0.4 %
    assert format_percent(5, 0) == "0 %"
    assert format_percent(None, None) == "0 %"


def test_ratio_is_two_absolute_numbers():
    assert format_ratio(763, 34) == "763 / 34"
    assert format_ratio(1234, None) == "1.234 / 0"


def test_invalid_metric_is_rejected():
    with pytest.raises(ValueError, match="invalid column"):
        KpiMetric(kpi_key="x", metric_type="percent", numerator_columns=("y; DROP TABLE t",))
    with pytest.raises(ValueError, match="unknown metric_type"):
        KpiMetric(kpi_key="x", metric_type="median")


def test_metric_survives_the_plan_to_render_event():
    metric = KpiMetric(kpi_key=KPIS[1].id, metric_type="percent", numerator_columns=("BearbSynchron",), denominator_columns=("y",))
    kpi = dataclasses.replace(KPIS[1], metric=metric)
    event = json.loads(json.dumps(dataclasses.asdict(kpi)))
    assert _kpi_from_event(event) == kpi


def _row(id_, key, metric_type, **kw):
    return {
        "id": id_, "kpi_key": key, "metric_type": metric_type,
        "numerator_columns": kw.get("num"), "numerator_not_null_column": kw.get("not_null"),
        "denominator_columns": kw.get("den"), "label": kw.get("label"),
        "explanation_text": kw.get("text"), "is_active": kw.get("active", True),
    }


def test_load_metrics_from_the_control_table(data_repo):
    data_repo.database.create_all_tables()
    data_repo.write_table(
        model=AutoreportKpiMetrics,
        df=pd.DataFrame([
            _row(1, "uvb_fehlercode", "percent", num="y", not_null="GrauUVB", den="y", text="Anteil grauer BKAs"),
            _row(2, "kapazitaet_saisonalitaet", "percent", num="Kap2to5, Kap6to10,KapOver10", den="y"),
            _row(3, "rote_bka", "ratio", den="RedOver52"),
            _row(4, "bka_abgleichstatus", "percent", num="Rot", den="y", active=False),
            _row(5, "bka_bearbeitungsstatus", "percent", num="x]; DROP TABLE y--", den="y"),
        ]),
    )

    metrics = load_kpi_metrics()

    assert sorted(metrics) == ["kapazitaet_saisonalitaet", "rote_bka", "uvb_fehlercode"]  # inactive/invalid ignored
    assert metrics["uvb_fehlercode"].numerator_not_null_column == "GrauUVB"
    assert metrics["uvb_fehlercode"].explanation_text == "Anteil grauer BKAs"
    assert metrics["kapazitaet_saisonalitaet"].numerator_columns == ("Kap2to5", "Kap6to10", "KapOver10")
    assert metrics["rote_bka"].numerator_columns == () and metrics["rote_bka"].label == ""

    kpis = attach_metrics(KPIS, metrics)
    assert {k.id for k in kpis if k.metric is not None} == set(metrics)


def test_missing_table_means_no_metrics(data_repo):
    data_repo.database.create_all_tables()
    with data_repo.database.engine.begin() as con:
        con.exec_driver_sql("DROP TABLE IF EXISTS control.T_Control_Autoreport_KpiMetrics")
    assert load_kpi_metrics() == {}
