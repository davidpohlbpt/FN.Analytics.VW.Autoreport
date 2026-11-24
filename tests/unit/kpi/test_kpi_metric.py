"""KpiMetric: formatting, validation and loading from T_Control_Autoreport_KpiMetrics."""

import pandas as pd
import pytest

from pptcreator.kpi.kpi_metric import (
    KpiMetric,
    attach_metrics,
    format_percent,
    format_ratio,
    load_kpi_metrics,
)
from pptcreator.kpi.leitstand_source import format_age
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


def _row(id_, key, metric_type, **kw):
    return {
        "id": id_, "kpi_key": key, "metric_type": metric_type,
        "numerator_columns": kw.get("num"), "numerator_not_null_column": kw.get("not_null"),
        "denominator_columns": kw.get("den"), "label": kw.get("label"),
        "explanation_text_de": kw.get("text"), "showed_bkas_de": kw.get("showed_bkas"),
        "explanation_text_en": kw.get("text_en"), "showed_bkas_en": kw.get("showed_bkas_en"),
        "is_active": kw.get("active", True),
    }


def test_load_metrics_from_the_control_table(data_repo):
    data_repo.database.create_all_tables()
    data_repo.write_table(
        model=AutoreportKpiMetrics,
        df=pd.DataFrame([
            _row(1, "uvb_fehlercode", "percent", num="y", not_null="GrauUVB", den="y", text="Anteil grauer BKAs",
                 showed_bkas="alle BKAs mit UVB Fehlern"),
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
    assert metrics["uvb_fehlercode"].showed_bkas == "alle BKAs mit UVB Fehlern"
    assert metrics["rote_bka"].showed_bkas == ""
    assert metrics["kapazitaet_saisonalitaet"].numerator_columns == ("Kap2to5", "Kap6to10", "KapOver10")
    assert metrics["rote_bka"].numerator_columns == () and metrics["rote_bka"].label == ""

    kpis = attach_metrics(KPIS, metrics)
    assert {k.id for k in kpis if k.metric is not None} == set(metrics)


def test_english_texts_come_from_the_en_columns_with_german_fallback(data_repo):
    data_repo.database.create_all_tables()
    data_repo.write_table(
        model=AutoreportKpiMetrics,
        df=pd.DataFrame([
            _row(1, "rote_bka", "ratio", den="RedOver52", text="Anzahl rote BKAs",
                 text_en="Number of red BKAs", showed_bkas="alle BKAs mit roten Wochen"),
        ]),
    )

    english = load_kpi_metrics("EN")["rote_bka"]

    assert english.explanation_text == "Number of red BKAs"
    assert english.showed_bkas == "alle BKAs mit roten Wochen"  # no showed_bkas_en -> German
    assert load_kpi_metrics("DE")["rote_bka"].explanation_text == "Anzahl rote BKAs"


def test_english_number_and_age_formats():
    assert KpiMetric("rote_bka", "ratio").format(1200, 30, language="EN") == "1,200 / 30"
    assert KpiMetric("rote_bka", "ratio").format(1200, 30) == "1.200 / 30"
    assert format_age(400, "EN") == "1 year, 1 month"
    assert format_age(400) == "1 Jahr, 1 Monat"


def test_missing_table_means_no_metrics(data_repo):
    data_repo.database.create_all_tables()
    with data_repo.database.engine.begin() as con:
        con.exec_driver_sql("DROP TABLE IF EXISTS control.T_Control_Autoreport_KpiMetrics")
    assert load_kpi_metrics() == {}
