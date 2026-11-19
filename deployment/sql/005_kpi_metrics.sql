-- Value under each donut per KPI (ReportDB, schema control). SQL Server syntax.
-- Additive only: T_Control_Autoreport_Mappings.average_label stays as the fallback for
-- KPIs without an active row here (and for stages that never ran this script).
-- See pptcreator/kpi/kpi_metric.py.
--
-- Every value uses the donut's filter on ReportDB.dbo.T_RESULT_Leitstand_Overview:
--   MOD = 'Alle' AND AnalyseZeitpunkt = <snapshot> AND EK_ORG = <brand>
-- once for the brand total (overview slide) and once per COM (detail slides).
--
--   metric_type                 avg_age | percent | ratio | count
--   numerator_columns           comma-separated columns, summed per row; NULL = donut total
--   numerator_not_null_column   only rows where this column IS NOT NULL count (numerator)
--   denominator_columns         comma-separated columns, summed per row; NULL = donut total
--   label                       prefix in front of the value (e.g. 'Ø'); NULL = value only
--   explanation_text            text of the template's {kpi_explanation} token (overview + COM slides)
--
-- Formats: percent '45 %' (whole number), ratio '120 / 30', count '1.234'.
-- Denominator 0 / no data: '0 %' resp. '0 / 0'. No SQL is ever stored here: column names
-- are validated (letters, digits, '_' only) and invalid rows are ignored with a warning.

IF OBJECT_ID('control.T_Control_Autoreport_KpiMetrics', 'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_KpiMetrics (
    id                        INT IDENTITY(1,1) PRIMARY KEY,
    kpi_key                   NVARCHAR(100) NOT NULL,   -- = T_Control_Autoreport_Mappings.kpi_key
    metric_type               NVARCHAR(20)  NOT NULL,
    numerator_columns         NVARCHAR(500) NULL,
    numerator_not_null_column NVARCHAR(100) NULL,
    denominator_columns       NVARCHAR(500) NULL,
    label                     NVARCHAR(50)  NULL,
    explanation_text          NVARCHAR(500) NULL,
    is_active                 BIT           NOT NULL CONSTRAINT DF_Autoreport_KpiMetrics_Active DEFAULT 1,
    CONSTRAINT CK_Autoreport_KpiMetrics_Type CHECK (metric_type IN (N'avg_age', N'percent', N'ratio', N'count'))
);
GO

-- One active row per KPI
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UQ_Autoreport_KpiMetrics_ActiveKey')
CREATE UNIQUE INDEX UQ_Autoreport_KpiMetrics_ActiveKey
    ON control.T_Control_Autoreport_KpiMetrics (kpi_key) WHERE is_active = 1;
GO

-- ---------------------------------- Seed ------------------------------------- #
-- Rote BKAs: numerator NULL = the donut total (Red0to10 + Red11to52 + RedOver52).
-- The column is RedOver52 (> 52 weeks); the explanation intentionally says '>53W'.
INSERT INTO control.T_Control_Autoreport_KpiMetrics
    (kpi_key, metric_type, numerator_columns, numerator_not_null_column, denominator_columns, label, explanation_text, is_active)
SELECT v.kpi_key, v.metric_type, v.numerator_columns, v.numerator_not_null_column, v.denominator_columns, v.label, v.explanation_text, 1
FROM (VALUES
    (N'bka_aktualisierung',       N'avg_age', NULL,                              NULL,      NULL,        N'Ø',  N'Durchschnittliches BKA Alter seit der letzten Aktualisierung'),
    (N'bka_bearbeitungsstatus',   N'percent', N'BearbSynchron',                  NULL,      N'y',        NULL,  N'synchron (beidseitig bestätigt)'),
    (N'uvb_fehlercode',           N'percent', N'y',                              N'GrauUVB', N'y',       NULL,  N'Anteil grauer BKAs'),
    (N'rote_bka',                 N'ratio',   NULL,                              NULL,      N'RedOver52', NULL, N'Anzahl rote BKAs / BKA >53W'),
    (N'bka_abgleichstatus',       N'percent', N'Rot',                            NULL,      N'y',        NULL,  N'Anteil rote BKAs'),
    (N'kapazitaet_saisonalitaet', N'percent', N'Kap2to5,Kap6to10,KapOver10',     NULL,      N'y',        NULL,  N'Anteil ≥2 Einträge')
) AS v(kpi_key, metric_type, numerator_columns, numerator_not_null_column, denominator_columns, label, explanation_text)
WHERE NOT EXISTS (
    SELECT 1 FROM control.T_Control_Autoreport_KpiMetrics m WHERE m.kpi_key = v.kpi_key
);
GO
