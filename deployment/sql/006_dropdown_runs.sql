-- Week dropdowns of the frontend = the Control Center runs in the data. SQL Server syntax.
--
-- Frontend shows and stores 'LAUFKENNUNG (LAUF_KW)', e.g. 'V01-B (46/2025)', in
-- control.T_Control_Autoreport_Recipients.report_week / comparison_week. The backend
-- (pptcreator/kpi/base.py ReportPeriod, leitstand_source.resolve_date) splits the string
-- and finds the snapshot by LAUFKENNUNG + LAUF_KW (LAUFKENNUNG alone repeats every year).
--
-- dbo.V_Autoreport_DropdownValues reads the runs live from T_RESULT_Leitstand_Overview, so
-- every new weekly load appears in the dropdowns automatically; nothing has to be
-- maintained. control.T_Control_Autoreport_Weeks is no longer used (not dropped).
--   report_week      all runs
--   comparison_week  all runs except the latest one
--   sort_date        AnalyseZeitpunkt of the run (NULL for brand rows). A view cannot carry
--                    an order: the frontend sorts by it via its data source config
--                    (T_CONTROL_Report_DataSourceColumns, set at the end of this script).
-- Snapshots without LAUFKENNUNG / LAUF_KW (Jul-Sep 2024) are not offered.

-- ------------------------------- Recipients -------------------------------- #
-- Stages created from 001/003 have primary_date / reference_date: rename them to the
-- frontend's column names. Stages created by the frontend already have them.
IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'report_week') IS NULL
   AND COL_LENGTH('control.T_Control_Autoreport_Recipients', 'primary_date') IS NOT NULL
    EXEC sp_rename 'control.T_Control_Autoreport_Recipients.primary_date', 'report_week', 'COLUMN';
IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'comparison_week') IS NULL
   AND COL_LENGTH('control.T_Control_Autoreport_Recipients', 'reference_date') IS NOT NULL
    EXEC sp_rename 'control.T_Control_Autoreport_Recipients.reference_date', 'comparison_week', 'COLUMN';
GO

-- 'V01-B (46/2025)' is exactly 15 characters; a longer LAUFKENNUNG must not be cut off
IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'report_week') < 100   -- bytes (NVARCHAR(50) = 100)
    ALTER TABLE control.T_Control_Autoreport_Recipients ALTER COLUMN report_week NVARCHAR(50) NOT NULL;
IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'comparison_week') < 100
    ALTER TABLE control.T_Control_Autoreport_Recipients ALTER COLUMN comparison_week NVARCHAR(50) NOT NULL;

-- Soft delete of the frontend; the planner skips deleted rows
IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'IsDeleted') IS NULL
    ALTER TABLE control.T_Control_Autoreport_Recipients
        ADD IsDeleted BIT NOT NULL CONSTRAINT DF_Autoreport_Recipients_IsDeleted DEFAULT 0;
GO

-- ------------------------------ Dropdown view ------------------------------ #
CREATE OR ALTER VIEW dbo.V_Autoreport_DropdownValues
AS
WITH runs AS (
    SELECT AnalyseZeitpunkt,
           CAST(CONCAT(LTRIM(RTRIM(MAX(LAUFKENNUNG))), N' (', LTRIM(RTRIM(MAX(LAUF_KW))), N')') AS nvarchar(50)) AS run_label
    FROM dbo.T_RESULT_Leitstand_Overview
    WHERE LAUFKENNUNG IS NOT NULL AND LAUF_KW IS NOT NULL
    GROUP BY AnalyseZeitpunkt
),
labelled AS (
    SELECT AnalyseZeitpunkt, run_label,
           CASE WHEN AnalyseZeitpunkt = MAX(AnalyseZeitpunkt) OVER () THEN 1 ELSE 0 END AS is_latest
    FROM runs
)
SELECT CAST(b.brand_name AS nvarchar(200)) AS brand_name,
       CAST(NULL AS nvarchar(50))          AS report_week,
       CAST(NULL AS nvarchar(50))          AS comparison_week,
       CAST(0 AS bit)                      AS IsDeleted,
       CAST(NULL AS date)                  AS sort_date
FROM control.T_Control_Autoreport_Brands b
WHERE b.is_active = 1
UNION ALL
SELECT NULL, l.run_label, NULL, CAST(0 AS bit), CAST(l.AnalyseZeitpunkt AS date)
FROM labelled l
UNION ALL
SELECT NULL, NULL, l.run_label, CAST(0 AS bit), CAST(l.AnalyseZeitpunkt AS date)
FROM labelled l
WHERE l.is_latest = 0
UNION ALL
SELECT
    NULL AS brand_name,
    CAST(N'Aktuelle Woche' AS nvarchar(50)) AS report_week,
    NULL AS comparison_week,
    CAST(0 AS bit) AS IsDeleted,
    CAST(NULL AS date) AS sort_date;
GO

-- ------------------------ Frontend sort configuration ---------------------- #
-- The frontend sorts a data source by T_CONTROL_Report_DataSourceColumns.OrderBy (priority)
-- and OrderParameter (ASC/DESC). Data source 9502 = V_Autoreport_DropdownValues:
--   1. sort_date DESC   newest run first (hidden column)
--   2. brand_name ASC   brand rows have no sort_date; keeps the brand list alphabetical
-- The row is a copy of comparison_week's config, so all other settings match.
IF NOT EXISTS (SELECT 1 FROM dbo.T_CONTROL_Report_DataSourceColumns
               WHERE ReportDataSourceID = 9502 AND ColumnName = 'sort_date')
BEGIN
    SET IDENTITY_INSERT dbo.T_CONTROL_Report_DataSourceColumns ON;
    INSERT INTO dbo.T_CONTROL_Report_DataSourceColumns
        (ReportDataSourceColumnsID, ColumnName, DataType, Displayed, Sortable, Filterable,
         ColumnNameTranslationKey, LineBreak, ColumnStyle, NumberLocaleFormat, CurrencyTK, Editable,
         ReportDataSourceID, DisplayOrder, ColorCoded, OrderBy, OrderParameter, IsPrimaryKey, ValueSourceColumnId)
    SELECT 950204, 'sort_date', 'date', 0, 0, 0,
           NULL, LineBreak, ColumnStyle, NumberLocaleFormat, CurrencyTK, 0,
           ReportDataSourceID, 4, ColorCoded, 1, 'DESC', IsPrimaryKey, NULL
    FROM dbo.T_CONTROL_Report_DataSourceColumns
    WHERE ReportDataSourceColumnsID = 950203;
    SET IDENTITY_INSERT dbo.T_CONTROL_Report_DataSourceColumns OFF;
END

UPDATE dbo.T_CONTROL_Report_DataSourceColumns
SET OrderBy = 2, OrderParameter = 'ASC'
WHERE ReportDataSourceID = 9502 AND ColumnName = 'brand_name'
  AND (OrderBy IS NULL OR OrderBy <> 2 OR OrderParameter IS NULL OR OrderParameter <> 'ASC');
GO
