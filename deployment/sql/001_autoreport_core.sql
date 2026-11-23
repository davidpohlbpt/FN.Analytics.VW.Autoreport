-- Fresh ReportDB setup for VW Autoreport. Run before 002_autoreport_frontend.sql.
-- Replace both PROD S3 values below before executing. This script never seeds recipients.
-- The legacy dbo.T_RESULT_AutoReportRecipients table is intentionally not referenced.

USE ReportDB;
GO

IF OBJECT_ID(N'tempdb..#AutoreportDeploymentConfig') IS NOT NULL
    DROP TABLE #AutoreportDeploymentConfig;
CREATE TABLE #AutoreportDeploymentConfig (
    template_link NVARCHAR(1000) NOT NULL,
    target_location NVARCHAR(1000) NOT NULL
);
INSERT INTO #AutoreportDeploymentConfig (template_link, target_location)
VALUES (N'__SET_PROD_TEMPLATE_S3_URI__', N'__SET_PROD_REPORTS_S3_URI__');

IF OBJECT_ID(N'dbo.T_RESULT_Leitstand_Overview', N'U') IS NULL
    THROW 50000, 'ReportDB.dbo.T_RESULT_Leitstand_Overview must exist before Autoreport setup.', 1;
IF EXISTS (
    SELECT 1 FROM #AutoreportDeploymentConfig
    WHERE LEFT(template_link, 2) = N'__'
       OR LEFT(target_location, 2) = N'__'
       OR template_link NOT LIKE N's3://%'
       OR target_location NOT LIKE N's3://%'
)
    THROW 50001, 'Set the PROD template_link and target_location in this script before execution.', 1;
GO

IF SCHEMA_ID(N'control') IS NULL
   AND OBJECT_ID(N'dbo.T_RESULT_Leitstand_Overview', N'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM #AutoreportDeploymentConfig
       WHERE LEFT(template_link, 2) = N'__'
          OR LEFT(target_location, 2) = N'__'
          OR template_link NOT LIKE N's3://%'
          OR target_location NOT LIKE N's3://%'
   )
    EXEC(N'CREATE SCHEMA control');
GO

DECLARE @template_link NVARCHAR(1000);
DECLARE @target_location NVARCHAR(1000);
DECLARE @template_id INT;

SELECT @template_link = template_link, @target_location = target_location
FROM #AutoreportDeploymentConfig;

IF OBJECT_ID(N'dbo.T_RESULT_Leitstand_Overview', N'U') IS NULL
    THROW 50000, 'ReportDB.dbo.T_RESULT_Leitstand_Overview must exist before Autoreport setup.', 1;
IF LEFT(@template_link, 2) = N'__'
   OR LEFT(@target_location, 2) = N'__'
   OR @template_link NOT LIKE N's3://%'
   OR @target_location NOT LIKE N's3://%'
    THROW 50001, 'Set the PROD template_link and target_location in this script before execution.', 1;

IF OBJECT_ID(N'control.T_Control_Autoreport_Templates', N'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_Templates (
    id                         INT IDENTITY(1,1) PRIMARY KEY,
    name                       NVARCHAR(200)  NOT NULL,
    template_link              NVARCHAR(1000) NOT NULL,
    language                   NVARCHAR(2)    NOT NULL CONSTRAINT CK_Autoreport_Templates_Lang CHECK (language IN (N'DE', N'EN')),
    target_file_name           NVARCHAR(500)  NOT NULL,
    target_location            NVARCHAR(1000) NULL,
    commodity_charts_per_slide INT            NULL,
    email_subject              NVARCHAR(500)  NULL,
    is_active                  BIT            NOT NULL CONSTRAINT DF_Autoreport_Templates_Active DEFAULT 1
);

IF OBJECT_ID(N'control.T_Control_Autoreport_Mappings', N'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_Mappings (
    id             INT IDENTITY(1,1) PRIMARY KEY,
    template_id    INT            NOT NULL REFERENCES control.T_Control_Autoreport_Templates(id),
    kpi_key        NVARCHAR(100)  NOT NULL,
    kpi_order      INT            NOT NULL CONSTRAINT DF_Autoreport_Mappings_Order DEFAULT 0,
    kpi_name       NVARCHAR(200)  NOT NULL,
    slide_title    NVARCHAR(500)  NOT NULL,
    slide_subtitle NVARCHAR(1000) NULL,
    source         NVARCHAR(20)   NOT NULL CONSTRAINT CK_Autoreport_Mappings_Source CHECK (source IN (N'leitstand', N'frontend', N'backend', N'stub')),
    menu_item_id   INT            NULL,
    report_id      INT            NULL,
    tile_id        INT            NULL,
    chart_id       INT            NULL,
    query_key      NVARCHAR(100)  NULL,
    palette_json   NVARCHAR(2000) NULL,
    average_label  NVARCHAR(20)   NULL CONSTRAINT DF_Autoreport_Mappings_Avg DEFAULT N'Ø',
    is_active      BIT            NOT NULL CONSTRAINT DF_Autoreport_Mappings_Active DEFAULT 1,
    CONSTRAINT UQ_Autoreport_Mappings UNIQUE (template_id, kpi_key)
);

IF OBJECT_ID(N'control.T_Control_Autoreport_Brands', N'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_Brands (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    brand_name   NVARCHAR(200) NOT NULL,
    filter_value NVARCHAR(200) NOT NULL,
    is_active    BIT           NOT NULL CONSTRAINT DF_Autoreport_Brands_Active DEFAULT 1,
    CONSTRAINT UQ_Autoreport_Brands_Filter UNIQUE (filter_value)
);

IF OBJECT_ID(N'control.T_Control_Autoreport_Recipients', N'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_Recipients (
    id             INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    template_id    INT            NOT NULL CONSTRAINT DF_Autoreport_Recipients_Template DEFAULT 1
                                   REFERENCES control.T_Control_Autoreport_Templates(id),
    email          NVARCHAR(1000) NOT NULL,
    brand_id       INT            NULL REFERENCES control.T_Control_Autoreport_Brands(id),
    report_week    NVARCHAR(50)   NOT NULL,
    comparison_week NVARCHAR(50)  NOT NULL,
    send_now       BIT            NOT NULL CONSTRAINT DF_Autoreport_Recipients_SendNow DEFAULT 0,
    last_report_time DATETIME2    NULL,
    brand_name     NVARCHAR(200)  NULL,
    IsDeleted      BIT            NOT NULL CONSTRAINT DF_Autoreport_Recipients_IsDeleted DEFAULT 0,
    -- Required as the generic frontend editor's unique row key.
    RowID          AS (id)
);

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'control.T_Control_Autoreport_Recipients')
      AND name = N'UX_Autoreport_Recipients_RowID'
)
    CREATE UNIQUE INDEX UX_Autoreport_Recipients_RowID
        ON control.T_Control_Autoreport_Recipients (RowID);
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'control.T_Control_Autoreport_Recipients')
      AND name = N'IX_Autoreport_Recipients_SendNow'
)
    CREATE INDEX IX_Autoreport_Recipients_SendNow
        ON control.T_Control_Autoreport_Recipients (template_id)
        WHERE send_now = 1;

IF OBJECT_ID(N'control.T_Control_Autoreport_Runs', N'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_Runs (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    run_id           NVARCHAR(100)  NOT NULL,
    template_id      INT            NOT NULL,
    recipients       NVARCHAR(1000) NULL,
    recipient_id     INT            NULL,
    brand            NVARCHAR(200)  NOT NULL,
    current_period   NVARCHAR(50)   NULL,
    reference_period NVARCHAR(50)   NULL,
    status           NVARCHAR(20)   NOT NULL,
    error            NVARCHAR(4000) NULL,
    created_at       DATETIME2      NULL,
    updated_at       DATETIME2      NULL
);
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'control.T_Control_Autoreport_Runs')
      AND name = N'IX_Autoreport_Runs_RunId'
)
    CREATE INDEX IX_Autoreport_Runs_RunId
        ON control.T_Control_Autoreport_Runs (run_id);
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'control.T_Control_Autoreport_Runs')
      AND name = N'IX_Autoreport_Runs_OpenClaim'
)
    CREATE INDEX IX_Autoreport_Runs_OpenClaim
        ON control.T_Control_Autoreport_Runs (recipient_id)
        WHERE status = N'processing';

IF OBJECT_ID(N'control.T_Control_Autoreport_BrandCommodities', N'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_BrandCommodities (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    brand_id     INT          NOT NULL REFERENCES control.T_Control_Autoreport_Brands(id),
    com_source   NVARCHAR(50) NOT NULL,
    com_label    NVARCHAR(50) NOT NULL,
    sort_order   INT          NOT NULL CONSTRAINT DF_Autoreport_BrandCommodities_Order DEFAULT 0,
    show_if_zero BIT          NOT NULL CONSTRAINT DF_Autoreport_BrandCommodities_Zero DEFAULT 1,
    is_active    BIT          NOT NULL CONSTRAINT DF_Autoreport_BrandCommodities_Active DEFAULT 1,
    CONSTRAINT UQ_Autoreport_BrandCommodities UNIQUE (brand_id, com_source)
);

IF OBJECT_ID(N'control.T_Control_Autoreport_BrandFeatures', N'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_BrandFeatures (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    brand_id      INT           NOT NULL REFERENCES control.T_Control_Autoreport_Brands(id),
    feature_key   NVARCHAR(50)  NOT NULL,
    feature_value NVARCHAR(200) NOT NULL,
    is_active     BIT           NOT NULL CONSTRAINT DF_Autoreport_BrandFeatures_Active DEFAULT 1,
    CONSTRAINT UQ_Autoreport_BrandFeatures UNIQUE (brand_id, feature_key)
);

IF OBJECT_ID(N'control.T_Control_Autoreport_KpiMetrics', N'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_KpiMetrics (
    id                        INT IDENTITY(1,1) PRIMARY KEY,
    kpi_key                   NVARCHAR(100) NOT NULL,
    metric_type               NVARCHAR(20)  NOT NULL,
    numerator_columns         NVARCHAR(500) NULL,
    numerator_not_null_column NVARCHAR(100) NULL,
    denominator_columns       NVARCHAR(500) NULL,
    label                     NVARCHAR(50)  NULL,
    explanation_text          NVARCHAR(500) NULL,
    showed_bkas               NVARCHAR(200) NULL,
    is_active                 BIT           NOT NULL CONSTRAINT DF_Autoreport_KpiMetrics_Active DEFAULT 1,
    CONSTRAINT CK_Autoreport_KpiMetrics_Type CHECK (metric_type IN (N'avg_age', N'percent', N'ratio', N'count'))
);

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'control.T_Control_Autoreport_KpiMetrics')
      AND name = N'UQ_Autoreport_KpiMetrics_ActiveKey'
)
    CREATE UNIQUE INDEX UQ_Autoreport_KpiMetrics_ActiveKey
        ON control.T_Control_Autoreport_KpiMetrics (kpi_key)
        WHERE is_active = 1;


IF (SELECT COUNT(*) FROM control.T_Control_Autoreport_Templates
    WHERE name = N'IDM Control Center Weekly') > 1
    THROW 50002, 'More than one IDM Control Center Weekly template exists; resolve it before seeding.', 1;

SELECT @template_id = id
FROM control.T_Control_Autoreport_Templates
WHERE name = N'IDM Control Center Weekly';

IF @template_id IS NULL
BEGIN
    INSERT INTO control.T_Control_Autoreport_Templates
        (name, template_link, language, target_file_name, target_location, email_subject, is_active)
    VALUES
        (N'IDM Control Center Weekly', @template_link, N'DE',
         N'BKM_IDM_Control_Center_{brand}_{current}_vs_{reference}',
         @target_location,
         N'BKM IDM Autoreport: Control Center {brand}: {current} vs. {reference}', 1);
    SET @template_id = CONVERT(INT, SCOPE_IDENTITY());
END
ELSE IF EXISTS (
    SELECT 1
    FROM control.T_Control_Autoreport_Templates
    WHERE id = @template_id
      AND (template_link <> @template_link OR ISNULL(target_location, N'') <> @target_location)
)
    THROW 50003, 'The existing template has different S3 locations; verify PROD configuration before continuing.', 1;

SELECT @template_id = id
FROM control.T_Control_Autoreport_Templates
WHERE name = N'IDM Control Center Weekly';

IF @template_id IS NULL
    THROW 50004, 'The IDM Control Center Weekly template was not created.', 1;

IF EXISTS (
    SELECT 1
    FROM (VALUES
        (N'Audi', N'Audi'), (N'Audi Hungaria', N'Audi Hungaria'),
        (N'Audi Mexico', N'Audi Mexico'), (N'Bentley', N'Bentley'),
        (N'Cariad', N'Cariad'), (N'HT-Kapapfleger', N'HT-Kapapfleger'),
        (N'Lamborghini', N'Lamborghini'), (N'MAN', N'MAN'),
        (N'MAN Trucks Sp. z o.o.', N'MAN Trucks Sp. z o.o.'),
        (N'Porsche', N'Porsche'), (N'SEAT', N'SEAT'), (N'Skoda', N'Skoda'),
        (N'VW AR', N'VW AR'), (N'VW BR', N'VW BR'), (N'VW Eur', N'VW Eur'),
        (N'VW India', N'VW India'), (N'VW Mexico', N'VW Mexico'),
        (N'VW Nutzfahrzeuge', N'VWN'), (N'VW PKW', N'VW PKW'),
        (N'VW SA', N'VW SA'), (N'VW Tech Co.', N'VW Tech Co.'),
        (N'VW US', N'VW US'), (N'VW VC', N'VW VC')
    ) AS expected(brand_name, filter_value)
    JOIN control.T_Control_Autoreport_Brands existing
      ON existing.filter_value = expected.filter_value
    WHERE existing.brand_name <> expected.brand_name
)
    THROW 50005, 'An existing brand uses a different display name; reconcile the brand seed before continuing.', 1;

SET XACT_ABORT ON;
BEGIN TRANSACTION;

INSERT INTO control.T_Control_Autoreport_Brands (brand_name, filter_value, is_active)
SELECT v.brand_name, v.filter_value, 1
FROM (VALUES
    (N'Audi', N'Audi'), (N'Audi Hungaria', N'Audi Hungaria'),
    (N'Audi Mexico', N'Audi Mexico'), (N'Bentley', N'Bentley'),
    (N'Cariad', N'Cariad'), (N'HT-Kapapfleger', N'HT-Kapapfleger'),
    (N'Lamborghini', N'Lamborghini'), (N'MAN', N'MAN'),
    (N'MAN Trucks Sp. z o.o.', N'MAN Trucks Sp. z o.o.'),
    (N'Porsche', N'Porsche'), (N'SEAT', N'SEAT'), (N'Skoda', N'Skoda'),
    (N'VW AR', N'VW AR'), (N'VW BR', N'VW BR'), (N'VW Eur', N'VW Eur'),
    (N'VW India', N'VW India'), (N'VW Mexico', N'VW Mexico'),
    (N'VW Nutzfahrzeuge', N'VWN'), (N'VW PKW', N'VW PKW'),
    (N'VW SA', N'VW SA'), (N'VW Tech Co.', N'VW Tech Co.'),
    (N'VW US', N'VW US'), (N'VW VC', N'VW VC')
) AS v(brand_name, filter_value)
WHERE NOT EXISTS (
    SELECT 1 FROM control.T_Control_Autoreport_Brands b
    WHERE b.filter_value = v.filter_value
);

INSERT INTO control.T_Control_Autoreport_Mappings
    (template_id, kpi_key, kpi_order, kpi_name, slide_title, slide_subtitle, source,
     menu_item_id, report_id, tile_id, chart_id, average_label, is_active)
SELECT @template_id, v.kpi_key, v.kpi_order, v.kpi_name, v.slide_title, v.slide_subtitle,
       N'leitstand', 1200, 1200, v.chart_id, v.chart_id, v.average_label, 1
FROM (VALUES
    (N'bka_aktualisierung', 1, N'BKA nach Aktualisierung', N'BKA nach Aktualisierung',
     N'Wann wurden BKAs das letzte Mal bearbeitet und wie ist das durchschnittliche BKA Alter?', 12000, N'Ø'),
    (N'bka_bearbeitungsstatus', 2, N'BKA nach Bearbeitungsstatus', N'BKA nach Bearbeitungsstatus',
     N'In welchem Bearbeitungsstatus sind die BKAs aktuell?', 12002, NULL),
    (N'uvb_fehlercode', 3, N'UVB Fehler nach Fehlercode', N'Graue BKAs - UVB Fehler nach Fehlercode',
     N'Welche UVB Fehler liegen bei den grauen BKAs vor?', 12004, NULL),
    (N'rote_bka', 4, N'Rote BKAs', N'Rote BKAs',
     N'Welche BKAs haben mehr als 10 rote Wochen?', 12006, NULL),
    (N'bka_abgleichstatus', 5, N'BKA nach Abgleichstatus', N'BKA nach Abgleichstatus',
     N'Wie ist die Versorgungssituation laut Bedarfs-Kapazitäts-Abgleich?', 120013, NULL),
    (N'kapazitaet_saisonalitaet', 6, N'Saisonalität von Kapazitäten', N'Saisonalität in BKAs',
     N'Wie viele verschiedene Kapazitätseinträge sind in den BKAs vorhanden?', 120017, NULL)
) AS v(kpi_key, kpi_order, kpi_name, slide_title, slide_subtitle, chart_id, average_label)
WHERE NOT EXISTS (
    SELECT 1 FROM control.T_Control_Autoreport_Mappings m
    WHERE m.template_id = @template_id AND m.kpi_key = v.kpi_key
);

INSERT INTO control.T_Control_Autoreport_BrandCommodities
    (brand_id, com_source, com_label, sort_order, show_if_zero, is_active)
SELECT b.id, v.com_source, v.com_label, v.sort_order, 1, 1
FROM control.T_Control_Autoreport_Brands b
CROSS JOIN (VALUES
    (N'BC', N'BC', 10), (N'BI', N'BI', 20), (N'BM', N'BM', 30),
    (N'BN', N'BN', 40), (N'BX', N'BX', 50), (N'BP', N'CB', 60), (N'BL', N'ZB', 70)
) AS v(com_source, com_label, sort_order)
WHERE b.filter_value = N'VW PKW'
  AND NOT EXISTS (
      SELECT 1 FROM control.T_Control_Autoreport_BrandCommodities bc
      WHERE bc.brand_id = b.id AND bc.com_source = v.com_source
  );

INSERT INTO control.T_Control_Autoreport_BrandFeatures
    (brand_id, feature_key, feature_value, is_active)
SELECT b.id, N'footnote_text',
       N'Hinweis: Die Differenz zwischen Gesamt VW PKW und den COMs ergibt sich durch BKAs die abweichenden COMs (BA, SO, …) zugeordnet sind.',
       1
FROM control.T_Control_Autoreport_Brands b
WHERE b.filter_value = N'VW PKW'
  AND NOT EXISTS (
      SELECT 1 FROM control.T_Control_Autoreport_BrandFeatures bf
      WHERE bf.brand_id = b.id AND bf.feature_key = N'footnote_text'
  );

INSERT INTO control.T_Control_Autoreport_KpiMetrics
    (kpi_key, metric_type, numerator_columns, numerator_not_null_column,
     denominator_columns, label, explanation_text, showed_bkas, is_active)
SELECT v.kpi_key, v.metric_type, v.numerator_columns, v.numerator_not_null_column,
       v.denominator_columns, v.label, v.explanation_text, v.showed_bkas, 1
FROM (VALUES
    (N'bka_aktualisierung', N'avg_age', NULL, NULL, NULL, N'Ø',
     N'Durchschnittliches BKA Alter seit der letzten Aktualisierung', NULL),
    (N'bka_bearbeitungsstatus', N'percent', N'BearbSynchron', NULL, N'y', NULL,
     N'Anteil synchroner BKAs (beidseitig berstätigt)', NULL),
    (N'uvb_fehlercode', N'percent', N'y', N'GrauUVB', N'y', NULL,
     N'Anteil grauer BKAs', N'alle BKAs mit UVB Fehlern'),
    (N'rote_bka', N'ratio', NULL, NULL, N'RedOver52', NULL,
     N'Anzahl rote BKAs / BKA >53W', N'alle BKAs mit roten Wochen'),
    (N'bka_abgleichstatus', N'percent', N'Rot', NULL, N'y', NULL,
     N'Anteil rote BKAs', NULL),
    (N'kapazitaet_saisonalitaet', N'percent', N'Kap2to5,Kap6to10,KapOver10', NULL, N'y', NULL,
     N'Anteil ≥2 Einträge', NULL)
) AS v(kpi_key, metric_type, numerator_columns, numerator_not_null_column,
       denominator_columns, label, explanation_text, showed_bkas)
WHERE NOT EXISTS (
    SELECT 1 FROM control.T_Control_Autoreport_KpiMetrics m
    WHERE m.kpi_key = v.kpi_key
);

COMMIT TRANSACTION;
DROP TABLE #AutoreportDeploymentConfig;
GO

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
END;
GO

CREATE OR ALTER VIEW dbo.V_Autoreport_Recipients
AS
SELECT RowID, id, template_id, email, brand_id, brand_name,
       report_week, comparison_week, send_now, last_report_time, IsDeleted
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
       CAST(0 AS BIT) AS IsDeleted,
       CAST(NULL AS DATE) AS sort_date
FROM control.T_Control_Autoreport_Brands b
WHERE b.is_active = 1
UNION ALL
SELECT NULL, l.run_label, NULL, CAST(0 AS BIT), CAST(l.AnalyseZeitpunkt AS DATE)
FROM labelled l
UNION ALL
SELECT NULL, NULL, l.run_label, CAST(0 AS BIT), CAST(l.AnalyseZeitpunkt AS DATE)
FROM labelled l
WHERE l.is_latest = 0
UNION ALL
SELECT NULL, CAST(CONCAT(N'Aktuelle Woche ', l.run_label) AS NVARCHAR(50)),
       NULL, CAST(0 AS BIT), CAST(NULL AS DATE)
FROM labelled l
WHERE l.is_latest = 1
UNION ALL
SELECT NULL, CAST(N'Aktuelle Woche' AS NVARCHAR(50)), NULL, CAST(0 AS BIT), CAST(NULL AS DATE)
WHERE NOT EXISTS (SELECT 1 FROM labelled WHERE is_latest = 1);
GO

-- Read-only verification queries; do not copy recipient data to validate deployment.
SELECT s.name AS schema_name, t.name AS table_name, COUNT(c.column_id) AS column_count
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.columns c ON c.object_id = t.object_id
WHERE s.name = N'control' AND t.name LIKE N'T[_]Control[_]Autoreport%'
GROUP BY s.name, t.name
ORDER BY t.name;

SELECT COUNT(*) AS active_brands FROM control.T_Control_Autoreport_Brands WHERE is_active = 1;
SELECT COUNT(*) AS active_kpi_mappings FROM control.T_Control_Autoreport_Mappings
WHERE template_id = (SELECT id FROM control.T_Control_Autoreport_Templates
                     WHERE name = N'IDM Control Center Weekly') AND is_active = 1;
SELECT name,type_desc FROM sys.objects
WHERE name IN (N'V_Autoreport_Recipients',N'V_Autoreport_DropdownValues',
               N'trg_Autoreport_Recipients_ResolveBrand');
GO
