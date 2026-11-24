-- English version of the VW Autoreport.
-- Prerequisite: 001_autoreport_core.sql and 002_autoreport_frontend.sql have run.
-- Idempotent: safe to re-run. Fresh setups run 001 -> 002 -> 003.
--
-- What it does:
--   1. Language-specific texts in the existing tables (breaking rename, deploy the code together):
--        KpiMetrics:    explanation_text -> explanation_text_de, showed_bkas -> showed_bkas_de,
--                       new explanation_text_en / showed_bkas_en (filled with English texts)
--        BrandFeatures: feature_key 'footnote_text' -> 'footnote_text_de', new 'footnote_text_en'
--   2. A second template 'IDM Control Center Weekly EN' (language EN, English .pptx) with
--      the same six KPIs as the German template and English slide titles.
--   3. Recipients get a 'language' column (DE/EN, default DE). The trigger resolves
--      template_id from it, so vw-autoreport-detect keeps reading template_id unchanged.
--   4. Frontend: a mandatory 'Report language' dropdown in the AutoReport recipient editor.
--
-- Before executing: upload the English template and set its S3 URI below.

USE ReportDB;
GO

IF OBJECT_ID(N'tempdb..#AutoreportEnglishConfig') IS NOT NULL
    DROP TABLE #AutoreportEnglishConfig;
CREATE TABLE #AutoreportEnglishConfig (template_link_en NVARCHAR(1000) NOT NULL);
-- >>> SET THIS VALUE: S3 URI of the uploaded English template <<<
INSERT INTO #AutoreportEnglishConfig (template_link_en)
VALUES (N's3://dqn-ingestion-bucket-int/VW-autoreport/templates/VW_Template_Overview_EN.pptx');
-- INT e.g. s3://dqn-ingestion-bucket-int/VW-autoreport/templates/VW_Template_Overview_EN.pptx

-- A THROW only stops its own batch. On a failed check, NOEXEC ON makes SQL Server skip every
-- following batch (they are only compiled), so nothing is changed; the end of the script resets it.
DECLARE @precheck_error NVARCHAR(400) =
    CASE
        WHEN EXISTS (SELECT 1 FROM #AutoreportEnglishConfig
                     WHERE LEFT(template_link_en, 2) = N'__' OR template_link_en NOT LIKE N's3://%')
            THEN N'Set the English template_link (s3://...) in this script before execution.'
        WHEN OBJECT_ID(N'control.T_Control_Autoreport_Templates', N'U') IS NULL
          OR OBJECT_ID(N'control.T_Control_Autoreport_Recipients', N'U') IS NULL
          OR OBJECT_ID(N'dbo.T_CONTROL_Report_DataSourceColumns', N'U') IS NULL
            THEN N'Run 001_autoreport_core.sql and 002_autoreport_frontend.sql first.'
        WHEN (SELECT COUNT(*) FROM control.T_Control_Autoreport_Templates
              WHERE name = N'IDM Control Center Weekly' AND language = N'DE') <> 1
            THEN N'Exactly one German template ''IDM Control Center Weekly'' is expected.'
        WHEN EXISTS (SELECT 1 FROM dbo.T_CONTROL_Report_DataSourceColumns
                     WHERE ReportDataSourceColumnsID IN (950107, 950205)
                       AND NOT (ColumnName = N'language' AND ReportDataSourceID IN (9501, 9502)))
            THEN N'Reserved frontend column IDs 950107/950205 are used by something else.'
    END;
IF @precheck_error IS NOT NULL
BEGIN
    RAISERROR(N'%s Nothing was changed; the rest of the script is skipped.', 16, 1, @precheck_error);
    SET NOEXEC ON;
END
GO

-- ------------------------------------------------------------------------------------
-- Schema
-- ------------------------------------------------------------------------------------

-- A THROW only stops its own batch, so batches with side effects re-check the config as well.
IF NOT EXISTS (SELECT 1 FROM #AutoreportEnglishConfig
               WHERE LEFT(template_link_en, 2) <> N'__' AND template_link_en LIKE N's3://%')
    THROW 50300, 'Set the English template_link (s3://...) in this script before execution.', 1;

IF COL_LENGTH(N'control.T_Control_Autoreport_KpiMetrics', N'explanation_text') IS NOT NULL
   AND COL_LENGTH(N'control.T_Control_Autoreport_KpiMetrics', N'explanation_text_de') IS NULL
    EXEC sp_rename N'control.T_Control_Autoreport_KpiMetrics.explanation_text', N'explanation_text_de', N'COLUMN';
IF COL_LENGTH(N'control.T_Control_Autoreport_KpiMetrics', N'showed_bkas') IS NOT NULL
   AND COL_LENGTH(N'control.T_Control_Autoreport_KpiMetrics', N'showed_bkas_de') IS NULL
    EXEC sp_rename N'control.T_Control_Autoreport_KpiMetrics.showed_bkas', N'showed_bkas_de', N'COLUMN';
IF COL_LENGTH(N'control.T_Control_Autoreport_KpiMetrics', N'explanation_text_en') IS NULL
    ALTER TABLE control.T_Control_Autoreport_KpiMetrics ADD explanation_text_en NVARCHAR(500) NULL;
IF COL_LENGTH(N'control.T_Control_Autoreport_KpiMetrics', N'showed_bkas_en') IS NULL
    ALTER TABLE control.T_Control_Autoreport_KpiMetrics ADD showed_bkas_en NVARCHAR(200) NULL;

IF COL_LENGTH(N'control.T_Control_Autoreport_Recipients', N'language') IS NULL
    ALTER TABLE control.T_Control_Autoreport_Recipients
        ADD language NVARCHAR(2) NOT NULL
            CONSTRAINT DF_Autoreport_Recipients_Language DEFAULT N'DE'
            CONSTRAINT CK_Autoreport_Recipients_Language CHECK (language IN (N'DE', N'EN'));
GO

-- ------------------------------------------------------------------------------------
-- English template, KPI mappings and texts
-- ------------------------------------------------------------------------------------

DECLARE @template_link_en NVARCHAR(1000) = (SELECT template_link_en FROM #AutoreportEnglishConfig);
DECLARE @de_id INT = (SELECT id FROM control.T_Control_Autoreport_Templates
                      WHERE name = N'IDM Control Center Weekly' AND language = N'DE');
DECLARE @en_id INT;

IF @template_link_en IS NULL OR LEFT(@template_link_en, 2) = N'__' OR @template_link_en NOT LIKE N's3://%'
    THROW 50300, 'Set the English template_link (s3://...) in this script before execution.', 1;
IF @de_id IS NULL
    THROW 50302, 'Exactly one German template ''IDM Control Center Weekly'' is expected.', 1;
IF (SELECT COUNT(*) FROM control.T_Control_Autoreport_Templates
    WHERE name = N'IDM Control Center Weekly EN') > 1
    THROW 50304, 'More than one IDM Control Center Weekly EN template exists; resolve it first.', 1;
IF EXISTS (SELECT 1 FROM control.T_Control_Autoreport_Templates
           WHERE name = N'IDM Control Center Weekly EN' AND template_link <> @template_link_en)
    THROW 50305, 'The existing English template has a different template_link; verify before continuing.', 1;

SET XACT_ABORT ON;
BEGIN TRANSACTION;

INSERT INTO control.T_Control_Autoreport_Templates
    (name, template_link, language, target_file_name, target_location,
     commodity_charts_per_slide, email_subject, is_active)
SELECT N'IDM Control Center Weekly EN', @template_link_en, N'EN',
       N'BKM_IDM_Control_Center_{brand}_{current}_vs_{reference}_EN',
       de.target_location, de.commodity_charts_per_slide,
       N'BKM IDM Autoreport: Control Center {brand}: {current} vs. {reference}', 1
FROM control.T_Control_Autoreport_Templates de
WHERE de.id = @de_id
  AND NOT EXISTS (SELECT 1 FROM control.T_Control_Autoreport_Templates
                  WHERE name = N'IDM Control Center Weekly EN');

SELECT @en_id = id FROM control.T_Control_Autoreport_Templates
WHERE name = N'IDM Control Center Weekly EN';

-- Same data configuration as the German template, English wording
INSERT INTO control.T_Control_Autoreport_Mappings
    (template_id, kpi_key, kpi_order, kpi_name, slide_title, slide_subtitle, source,
     menu_item_id, report_id, tile_id, chart_id, query_key, palette_json, average_label, is_active)
SELECT @en_id, de.kpi_key, de.kpi_order, v.kpi_name, v.slide_title, v.slide_subtitle, de.source,
       de.menu_item_id, de.report_id, de.tile_id, de.chart_id, de.query_key, de.palette_json,
       de.average_label, de.is_active
FROM control.T_Control_Autoreport_Mappings de
JOIN (VALUES
    (N'bka_aktualisierung', N'BKA by last update', N'BKA by last update',
     N'When were BKAs last edited and what is the average BKA age?'),
    (N'bka_bearbeitungsstatus', N'BKA by processing status', N'BKA by processing status',
     N'What processing status are the BKAs currently in?'),
    (N'uvb_fehlercode', N'UVB errors by error code', N'Grey BKAs - UVB errors by error code',
     N'Which UVB errors occur in the grey BKAs?'),
    (N'rote_bka', N'Red BKAs', N'Red BKAs',
     N'Which BKAs have more than 10 red weeks?'),
    (N'bka_abgleichstatus', N'BKA by reconciliation status', N'BKA by reconciliation status',
     N'What is the supply situation according to the demand-capacity reconciliation?'),
    (N'kapazitaet_saisonalitaet', N'Seasonality of capacities', N'Seasonality in BKAs',
     N'How many different capacity entries are there in the BKAs?')
) AS v(kpi_key, kpi_name, slide_title, slide_subtitle) ON v.kpi_key = de.kpi_key
WHERE de.template_id = @de_id
  AND NOT EXISTS (SELECT 1 FROM control.T_Control_Autoreport_Mappings m
                  WHERE m.template_id = @en_id AND m.kpi_key = de.kpi_key);

-- English KPI texts; only empty fields are filled, so manual corrections survive a re-run
UPDATE m
   SET explanation_text_en = COALESCE(m.explanation_text_en, v.explanation_text_en),
       showed_bkas_en      = COALESCE(m.showed_bkas_en, v.showed_bkas_en)
FROM control.T_Control_Autoreport_KpiMetrics m
JOIN (VALUES
    (N'bka_aktualisierung', N'Average BKA age since the last update', NULL),
    (N'bka_bearbeitungsstatus', N'Share of synchronous BKAs (confirmed on both sides)', NULL),
    (N'uvb_fehlercode', N'Share of grey BKAs', N'all BKAs with UVB errors'),
    (N'rote_bka', N'Number of red BKAs / BKA >53W', N'all BKAs with red weeks'),
    (N'bka_abgleichstatus', N'Share of red BKAs', NULL),
    (N'kapazitaet_saisonalitaet', N'Share ≥2 entries', NULL)
) AS v(kpi_key, explanation_text_en, showed_bkas_en) ON v.kpi_key = m.kpi_key
WHERE (m.explanation_text_en IS NULL AND v.explanation_text_en IS NOT NULL)
   OR (m.showed_bkas_en IS NULL AND v.showed_bkas_en IS NOT NULL);

-- Footnote per language: the existing German key gets the _de suffix, English is added
UPDATE control.T_Control_Autoreport_BrandFeatures
   SET feature_key = N'footnote_text_de'
 WHERE feature_key = N'footnote_text';

INSERT INTO control.T_Control_Autoreport_BrandFeatures (brand_id, feature_key, feature_value, is_active)
SELECT b.id, N'footnote_text_en',
       N'Note: The difference between total VW PKW and the COMs results from BKAs that are assigned to other COMs (BA, SO, …).',
       1
FROM control.T_Control_Autoreport_Brands b
WHERE b.filter_value = N'VW PKW'
  AND NOT EXISTS (SELECT 1 FROM control.T_Control_Autoreport_BrandFeatures bf
                  WHERE bf.brand_id = b.id AND bf.feature_key = N'footnote_text_en');

COMMIT TRANSACTION;
GO

-- ------------------------------------------------------------------------------------
-- Recipients: language -> template_id
-- ------------------------------------------------------------------------------------

CREATE OR ALTER TRIGGER control.trg_Autoreport_Recipients_ResolveBrand
ON control.T_Control_Autoreport_Recipients
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    IF TRIGGER_NESTLEVEL(@@PROCID) > 1 RETURN;

    UPDATE r
       SET brand_id = b.id
      FROM control.T_Control_Autoreport_Recipients r
      JOIN inserted i ON i.id = r.id
      JOIN control.T_Control_Autoreport_Brands b
        ON LTRIM(RTRIM(i.brand_name)) IN (b.brand_name, b.filter_value)
     WHERE b.is_active = 1
       AND (r.brand_id IS NULL OR r.brand_id <> b.id);

    -- The oldest active template of the chosen language (DE: id 1, EN: 'IDM Control Center Weekly EN')
    UPDATE r
       SET template_id = t.id
      FROM control.T_Control_Autoreport_Recipients r
      JOIN inserted i ON i.id = r.id
     CROSS APPLY (
           SELECT TOP 1 tt.id
           FROM control.T_Control_Autoreport_Templates tt
           WHERE tt.is_active = 1 AND tt.language = i.language
           ORDER BY tt.id
     ) t
     WHERE r.template_id <> t.id;
END;
GO

-- Existing rows: align template_id with their language (all DE today, so normally no-op)
UPDATE r
   SET template_id = t.id
  FROM control.T_Control_Autoreport_Recipients r
 CROSS APPLY (
       SELECT TOP 1 tt.id
       FROM control.T_Control_Autoreport_Templates tt
       WHERE tt.is_active = 1 AND tt.language = r.language
       ORDER BY tt.id
 ) t
 WHERE r.template_id <> t.id;
GO

CREATE OR ALTER VIEW dbo.V_Autoreport_Recipients
AS
SELECT RowID, id, template_id, email, brand_id, brand_name,
       report_week, comparison_week, language, send_now, last_report_time, IsDeleted
FROM control.T_Control_Autoreport_Recipients;
GO

CREATE OR ALTER VIEW dbo.V_Autoreport_DropdownValues
AS
WITH runs AS (
    SELECT AnalyseZeitpunkt,
           CAST(CONCAT(LTRIM(RTRIM(MAX(LAUFKENNUNG))), N' (',
                       LTRIM(RTRIM(MAX(LAUF_KW))), N')') AS NVARCHAR(50)) AS run_label
    FROM dbo.T_RESULT_Leitstand_Overview
    WHERE LAUFKENNUNG IS NOT NULL AND LAUF_KW IS NOT NULL
    GROUP BY AnalyseZeitpunkt
),
labelled AS (
    SELECT AnalyseZeitpunkt, run_label,
           CASE WHEN AnalyseZeitpunkt = MAX(AnalyseZeitpunkt) OVER () THEN 1 ELSE 0 END AS is_latest
    FROM runs
)
SELECT CAST(b.brand_name AS NVARCHAR(200)) AS brand_name,
       CAST(NULL AS NVARCHAR(50)) AS report_week,
       CAST(NULL AS NVARCHAR(50)) AS comparison_week,
       CAST(NULL AS NVARCHAR(2)) AS language,
       CAST(0 AS BIT) AS IsDeleted,
       CAST(NULL AS DATE) AS sort_date
FROM control.T_Control_Autoreport_Brands b
WHERE b.is_active = 1
UNION ALL
SELECT NULL, l.run_label, NULL, NULL, CAST(0 AS BIT), CAST(l.AnalyseZeitpunkt AS DATE)
FROM labelled l
UNION ALL
SELECT NULL, NULL, l.run_label, NULL, CAST(0 AS BIT), CAST(l.AnalyseZeitpunkt AS DATE)
FROM labelled l
WHERE l.is_latest = 0
UNION ALL
SELECT NULL, CAST(CONCAT(N'Aktuelle Woche ', l.run_label) AS NVARCHAR(50)),
       NULL, NULL, CAST(0 AS BIT), CAST(NULL AS DATE)
FROM labelled l
WHERE l.is_latest = 1
UNION ALL
SELECT NULL, CAST(N'Aktuelle Woche' AS NVARCHAR(50)), NULL, NULL, CAST(0 AS BIT), CAST(NULL AS DATE)
WHERE NOT EXISTS (SELECT 1 FROM labelled WHERE is_latest = 1)
UNION ALL
SELECT DISTINCT NULL, NULL, NULL, t.language, CAST(0 AS BIT), CAST(NULL AS DATE)
FROM control.T_Control_Autoreport_Templates t
WHERE t.is_active = 1;
GO

-- ------------------------------------------------------------------------------------
-- Frontend: 'Report language' column in the recipient editor (report 950)
-- ------------------------------------------------------------------------------------

IF NOT EXISTS (SELECT 1 FROM #AutoreportEnglishConfig
               WHERE LEFT(template_link_en, 2) <> N'__' AND template_link_en LIKE N's3://%')
   OR COL_LENGTH(N'control.T_Control_Autoreport_Recipients', N'language') IS NULL
   OR EXISTS (
       SELECT 1 FROM dbo.T_CONTROL_Report_DataSourceColumns
       WHERE ReportDataSourceColumnsID IN (950107, 950205)
         AND NOT (ColumnName = N'language' AND ReportDataSourceID IN (9501, 9502))
   )
    THROW 50306, 'Earlier part of this script did not complete; frontend configuration skipped.', 1;

SET XACT_ABORT ON;
BEGIN TRANSACTION;

SET IDENTITY_INSERT dbo.T_CONTROL_Report_DataSourceColumns ON;
INSERT INTO dbo.T_CONTROL_Report_DataSourceColumns
    (ReportDataSourceColumnsID, ColumnName, DataType, Displayed, Sortable, Filterable,
     ColumnNameTranslationKey, LineBreak, ColumnStyle, NumberLocaleFormat, CurrencyTK,
     Editable, ReportDataSourceID, DisplayOrder, ColorCoded, OrderBy, OrderParameter,
     IsPrimaryKey, ValueSourceColumnId)
SELECT v.*
FROM (VALUES
    (950205, N'language', N'string', 0, 0, 0, N'TN_AutoReport_Language', NULL, NULL, NULL, NULL, 0, 9502, 5, NULL, 0, NULL, NULL, NULL),
    (950107, N'language', N'string', 1, 1, 1, N'TN_AutoReport_Language', NULL, NULL, NULL, NULL, 1, 9501, 5, NULL, 0, NULL, NULL, 950205)
) AS v(ReportDataSourceColumnsID, ColumnName, DataType, Displayed, Sortable, Filterable,
       ColumnNameTranslationKey, LineBreak, ColumnStyle, NumberLocaleFormat, CurrencyTK,
       Editable, ReportDataSourceID, DisplayOrder, ColorCoded, OrderBy, OrderParameter,
       IsPrimaryKey, ValueSourceColumnId)
WHERE NOT EXISTS (SELECT 1 FROM dbo.T_CONTROL_Report_DataSourceColumns c
                  WHERE c.ReportDataSourceColumnsID = v.ReportDataSourceColumnsID);
SET IDENTITY_INSERT dbo.T_CONTROL_Report_DataSourceColumns OFF;

-- Language after the comparison week; send_now and last_report_time move one position right
UPDATE dbo.T_CONTROL_Report_DataSourceColumns SET DisplayOrder = 6 WHERE ReportDataSourceColumnsID = 950105;
UPDATE dbo.T_CONTROL_Report_DataSourceColumns SET DisplayOrder = 7 WHERE ReportDataSourceColumnsID = 950106;

INSERT INTO dbo.T_CONTROL_Report_DataSourceColumnsValidation
    (ReportDataSourceColumnsID, Mandatory, ValidationMappingID, ValidationValue, ErrorTranslationKey)
SELECT 950107, 1, 3, NULL, N'TN_ValueRequired'
WHERE NOT EXISTS (SELECT 1 FROM dbo.T_CONTROL_Report_DataSourceColumnsValidation
                  WHERE ReportDataSourceColumnsID = 950107 AND ValidationMappingID = 3);

DECLARE @tk TABLE (LanguageCode NVARCHAR(5), TranslationKey NVARCHAR(200), Value NVARCHAR(MAX));
INSERT INTO @tk (LanguageCode, TranslationKey, Value)
VALUES
    (N'EN', N'TN_AutoReport_Language', N'Report language'),
    (N'DE', N'TN_AutoReport_Language', N'Berichtssprache'),
    (N'EN', N'TN_Helptext_AutoReportRecipients_Main_Table', N'Brand, reporting week, comparison week and report language (DE/EN) must be chosen from the allowed values.'),
    (N'DE', N'TN_Helptext_AutoReportRecipients_Main_Table', N'Marke, Berichtswoche, Vergleichswoche und Berichtssprache (DE/EN) müssen aus den erlaubten Werten gewählt werden.');

DELETE t
FROM Translation.dbo.Translation t
JOIN @tk k ON k.LanguageCode = t.LanguageCode AND k.TranslationKey = t.TranslationKey;

INSERT INTO Translation.dbo.Translation (LanguageCode, TranslationKey, Value, IsPublic)
SELECT LanguageCode, TranslationKey, Value, 0 FROM @tk;

COMMIT TRANSACTION;
DROP TABLE #AutoreportEnglishConfig;
GO

-- Read-only verification
SELECT id, name, language, template_link, target_file_name, is_active
FROM control.T_Control_Autoreport_Templates ORDER BY id;
SELECT t.language, COUNT(*) AS active_kpi_mappings
FROM control.T_Control_Autoreport_Mappings m
JOIN control.T_Control_Autoreport_Templates t ON t.id = m.template_id
WHERE m.is_active = 1 GROUP BY t.language;
SELECT kpi_key, explanation_text_de, explanation_text_en, showed_bkas_de, showed_bkas_en
FROM control.T_Control_Autoreport_KpiMetrics WHERE is_active = 1 ORDER BY kpi_key;
SELECT brand_id, feature_key, feature_value FROM control.T_Control_Autoreport_BrandFeatures
WHERE feature_key LIKE N'footnote_text%' ORDER BY brand_id, feature_key;
SELECT language, template_id, COUNT(*) AS recipients
FROM control.T_Control_Autoreport_Recipients WHERE IsDeleted = 0 GROUP BY language, template_id;
SELECT ReportDataSourceColumnsID, ColumnName, DisplayOrder, ValueSourceColumnId
FROM dbo.T_CONTROL_Report_DataSourceColumns
WHERE ReportDataSourceID IN (9501, 9502) ORDER BY ReportDataSourceID, DisplayOrder;
GO

-- Re-enable execution for this session (switched off above when a pre-check failed)
SET NOEXEC OFF;
GO
