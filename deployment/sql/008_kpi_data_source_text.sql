-- Data source wording per KPI. Run after 005_kpi_metrics.sql and before deploying
-- the application that reads this column. Existing configured text is preserved.

IF COL_LENGTH('control.T_Control_Autoreport_KpiMetrics', 'showed_bkas') IS NULL
    ALTER TABLE control.T_Control_Autoreport_KpiMetrics ADD showed_bkas NVARCHAR(200) NULL;
GO

UPDATE control.T_Control_Autoreport_KpiMetrics
SET showed_bkas = CASE kpi_key
    WHEN N'rote_bka' THEN N'alle BKAs mit roten Wochen'
    WHEN N'uvb_fehlercode' THEN N'alle BKAs mit UVB Fehlern'
END
WHERE kpi_key IN (N'rote_bka', N'uvb_fehlercode')
  AND showed_bkas IS NULL;
GO
