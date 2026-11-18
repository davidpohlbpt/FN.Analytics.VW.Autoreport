SET XACT_ABORT ON;
BEGIN TRANSACTION;

/* =========================== IdentityServer =========================== */
SET IDENTITY_INSERT IdentityServer.dbo.T_CONTROL_GenericHeaderBar ON;
INSERT INTO IdentityServer.dbo.T_CONTROL_GenericHeaderBar
    (HeaderBarID, Report, PageURLEnding, HeaderTranslationKey, TimestampConfigurationID, ScenID)
VALUES (950, 'AutoReportRecipients_Main', 'GenericReport', 'TN_AutoReportRecipients_Main_Titel', NULL, NULL);
SET IDENTITY_INSERT IdentityServer.dbo.T_CONTROL_GenericHeaderBar OFF;

/* only Logout - AdvFilter removed (no filters configured, 940 has none either) */
SET IDENTITY_INSERT IdentityServer.dbo.T_CONTROL_HeaderBarFunctionality ON;
INSERT INTO IdentityServer.dbo.T_CONTROL_HeaderBarFunctionality
    (HeaderBarFunctionalityID, HeaderBarID, Functionality, Level, [Order])
VALUES (95001, 950, 'Logout', 0, 1);
SET IDENTITY_INSERT IdentityServer.dbo.T_CONTROL_HeaderBarFunctionality OFF;

SET IDENTITY_INSERT IdentityServer.dbo.MenuItem ON;
INSERT INTO IdentityServer.dbo.MenuItem
    (MenuItemID, MenuItemName, TranslationKey, URL, Permission, IsGeneric,
     Display, DisplayOrder, HeaderBarID, MenuCategoryID, ConfidentialityId)
VALUES (950, 'AutoReportRecipients_Main', 'TN_AutoReportRecipients_Main_Titel',
        '/data-quality/genericreport', 'AutoReportRecipientsClaim', 1,
        1, 2, 950, 24, 3);
SET IDENTITY_INSERT IdentityServer.dbo.MenuItem OFF;

/* ============================== ReportDB ============================== */
/* aligned with 940: ShouldIgnoreDefaultReportingUnit = 1 (table has no ReportingUnitID) */
SET IDENTITY_INSERT ReportDB.dbo.T_CONTROL_Report ON;
INSERT INTO ReportDB.dbo.T_CONTROL_Report
    (ReportID, ReportName, MenuItemID, MeasurementUnitRemWorkID, HasMask, HasNestedFilter,
     UnionFilteringType, ShouldIgnoreDefaultReportingUnit, LazyLoading)
VALUES (950, 'AutoReportRecipients_Main', 950, 1, NULL, NULL, NULL, 1, 1);
SET IDENTITY_INSERT ReportDB.dbo.T_CONTROL_Report OFF;

SET IDENTITY_INSERT ReportDB.dbo.T_CONTROL_Report_DataSource ON;
INSERT INTO ReportDB.dbo.T_CONTROL_Report_DataSource (ReportDataSourceID, DataSource, ReportID)
VALUES (9501, 'V_Autoreport_Recipients', 950);
SET IDENTITY_INSERT ReportDB.dbo.T_CONTROL_Report_DataSource OFF;

SET IDENTITY_INSERT ReportDB.dbo.T_CONTROL_Report_DataSourceColumns ON;
INSERT INTO ReportDB.dbo.T_CONTROL_Report_DataSourceColumns
 (ReportDataSourceColumnsID, ColumnName, DataType, Displayed, Sortable, Filterable, ColumnNameTranslationKey,
  LineBreak, ColumnStyle, NumberLocaleFormat, CurrencyTK, Editable, ReportDataSourceID, DisplayOrder,
  ColorCoded, OrderBy, OrderParameter, IsPrimaryKey)
VALUES
 (950100,'RowID',            'numeric', 0,1,1,'RowId',             NULL,NULL,NULL,NULL,0,9501,0,NULL,0,NULL,1),
 (950101,'email',            'string',  1,1,1,'TN_Email',          NULL,NULL,NULL,NULL,1,9501,1,NULL,1,'ASC',NULL),
 (950102,'brand_name',       'string',  1,1,1,'TN_Brand',          NULL,NULL,NULL,NULL,1,9501,2,NULL,0,NULL,NULL),
 (950103,'report_week',      'string',  1,1,1,'TN_Berichtswoche',  NULL,NULL,NULL,NULL,1,9501,3,NULL,0,NULL,NULL),
 (950104,'comparison_week',  'string',  1,1,1,'TN_Abgleichswoche', NULL,NULL,NULL,NULL,1,9501,4,NULL,0,NULL,NULL),
 (950105,'send_now',         'boolean', 1,1,1,'TN_SendNow',        NULL,NULL,NULL,NULL,1,9501,5,NULL,0,NULL,NULL),
 (950106,'last_report_time', 'datetime',1,1,1,'TN_LastReportTime', NULL,NULL,NULL,NULL,0,9501,6,NULL,0,NULL,NULL);
SET IDENTITY_INSERT ReportDB.dbo.T_CONTROL_Report_DataSourceColumns OFF;

/* validations: 3 = required, 2 = pattern (ValidationID is identity -> not set) */
DECLARE @brandRx nvarchar(max);
SELECT @brandRx = '^(' + STRING_AGG(REPLACE(v, '.', '\.'), '|') WITHIN GROUP (ORDER BY v) + ')$'
FROM (SELECT brand_name AS v FROM ReportDB.control.T_Control_Autoreport_Brands WHERE is_active = 1
      UNION
      SELECT filter_value     FROM ReportDB.control.T_Control_Autoreport_Brands WHERE is_active = 1) x;

INSERT INTO ReportDB.dbo.T_CONTROL_Report_DataSourceColumnsValidation
 (ReportDataSourceColumnsID, Mandatory, ValidationMappingID, ValidationValue, ErrorTranslationKey)
VALUES
 (950101,1,3,NULL,'TN_ValueRequired'),
 (950101,1,2,'^[^@\s]+@[^@\s]+\.[^@\s]+$','TN_EmailValidationAutoReport'),
 (950102,1,3,NULL,'TN_ValueRequired'),
 (950102,1,2,@brandRx,'TN_InvalidBrand'),
 (950103,1,3,NULL,'TN_ValueRequired'),
 (950103,1,2,'^(47/2026|48/2026|49/2026)$','TN_InvalidWeek'),   -- update weekly
 (950104,1,3,NULL,'TN_ValueRequired'),
 (950104,1,2,'^(46/2026|47/2026|48/2026)$','TN_InvalidWeek');   -- update weekly

/* send_now as icon instead of true/false: checkmark for 1, empty box for 0
   (FormattingID is identity -> not set) */
INSERT INTO ReportDB.dbo.T_CONTROL_Report_DataSourceColumnsFormatting
    (Style, Icon, Value, MappingType, ReportDataSourceColumnsID)
SELECT v.Style, v.Icon, v.Value, 'Equal', 950105
FROM (VALUES ('color:black', 'fa fa-check',    '1'),
             ('color:black', 'fa fa-square-o', '0')) v(Style, Icon, Value)
WHERE NOT EXISTS (SELECT 1 FROM ReportDB.dbo.T_CONTROL_Report_DataSourceColumnsFormatting f
                  WHERE f.ReportDataSourceColumnsID = 950105 AND f.Value = v.Value);

/* tiles */
SET IDENTITY_INSERT ReportDB.dbo.T_CONTROL_Layout_Tiles ON;
INSERT INTO ReportDB.dbo.T_CONTROL_Layout_Tiles
    (TileID, TileName, [Order], Display, TitleTK, HelpTextTK, GridHeight,
     HelperTitleTK, HelperTitleUnitTK, ReportID, ReportDataSourceID, TileTypeID)
VALUES
 (9501,'AutoReportRecipients_Main_Info',  1,1,'TN_AutoReportRecipients_Main_Info_Titel', NULL,
       'grid-item-heavier', NULL,NULL, 950, NULL, 7),
 (9502,'AutoReportRecipients_Main_Table', 2,1,'TN_AutoReportRecipients_Main_Table_Titel','TN_Helptext_AutoReportRecipients_Main_Table',
       'grid-item-tallest', NULL,NULL, 950, 9501, 2);
SET IDENTITY_INSERT ReportDB.dbo.T_CONTROL_Layout_Tiles OFF;

SET IDENTITY_INSERT ReportDB.dbo.T_CONTROL_Layout_Text ON;
INSERT INTO ReportDB.dbo.T_CONTROL_Layout_Text (TextId, TileID, Content)
VALUES (9501, 9501, 'TN_AutoReportRecipients_Main_Info_Text');
SET IDENTITY_INSERT ReportDB.dbo.T_CONTROL_Layout_Text OFF;

/* HasAuditing = 0: table has no LastEditedAt/By */
SET IDENTITY_INSERT ReportDB.dbo.T_CONTROL_Layout_Table ON;
INSERT INTO ReportDB.dbo.T_CONTROL_Layout_Table
    (TableID, ReportID, HasCheckbox, NoRowsCheckedTranslationKey, RowsCheckedTranslationKey,
     ColumnToAllowSelection, HasPagination, SelectionIcon, ReportDataSourceID,
     HasAuditing, HasColumnFilter, HasColumnFilterDynamicWidth, TileID)
VALUES (9501, 950, 0, NULL, NULL, NULL, 1, NULL, 9501, 0, 1, 1, 9502);
SET IDENTITY_INSERT ReportDB.dbo.T_CONTROL_Layout_Table OFF;

/* tile options: TileOptionID is identity -> not set. 16 does not exist; 28/29/30 like 940.
   No Excel export (8, 12) and no variant management (9): the defaults ('0') apply. */
INSERT INTO ReportDB.dbo.T_CONTROL_Layout_TileOption (TileID, OptionID, Value) VALUES
 (9502,  7, '1'),                          -- HasColumnSelection
 (9502, 17, 'ConfirmationDialogDelete'),   -- ConfirmationDialogDelete
 (9502, 28, 'AutoReportRecipientsClaim'),  -- GenericTableAddClaim
 (9502, 29, 'AutoReportRecipientsClaim'),  -- GenericTableEditClaim
 (9502, 30, 'AutoReportRecipientsClaim');  -- GenericTableDeleteClaim

/* ============================= Translation ============================ */
/* upsert: delete + insert, so re-running never creates duplicates */
DECLARE @tk TABLE (LanguageCode nvarchar(5), TranslationKey nvarchar(200), Value nvarchar(max));
INSERT INTO @tk VALUES
 ('EN','TN_AutoReportRecipients_Main_Titel','Auto Report Settings'),
 ('DE','TN_AutoReportRecipients_Main_Titel','Auto Report Einstellungen'),
 ('EN','TN_AutoReportRecipients_Main_Info_Titel','Information'),
 ('DE','TN_AutoReportRecipients_Main_Info_Titel','Information'),
 ('EN','TN_AutoReportRecipients_Main_Table_Titel','Autoreport Configuration'),
 ('DE','TN_AutoReportRecipients_Main_Table_Titel','Autoreport-Konfiguration'),
 ('EN','TN_Helptext_AutoReportRecipients_Main_Table','Brand, reporting week and comparison week must be chosen from the allowed values.'),
 ('DE','TN_Helptext_AutoReportRecipients_Main_Table','Marke, Berichtswoche und Vergleichswoche müssen aus den erlaubten Werten gewählt werden.'),
 ('EN','TN_AutoReportRecipients_Main_Info_Text','<p>Select brand, reporting week and comparison week.</p>'),
 ('DE','TN_AutoReportRecipients_Main_Info_Text','<p>Wählen Sie Marke, Berichtswoche und Vergleichswoche.</p>'),
 ('EN','TN_Brand','Purchasing organization'),
 ('DE','TN_Brand','Einkaufsorganisation'),
 ('EN','TN_Berichtswoche','Reporting week'),
 ('DE','TN_Berichtswoche','Berichtswoche'),
 ('EN','TN_Abgleichswoche','Comparison week'),
 ('DE','TN_Abgleichswoche','Vergleichswoche'),
 ('EN','TN_SendNow','Send report'),
 ('DE','TN_SendNow','Auswertung anfordern'),
 ('EN','TN_LastReportTime','Last request'),
 ('DE','TN_LastReportTime','Letzte Anforderung'),
 ('EN','TN_InvalidBrand','Please choose a brand from the list.'),
 ('DE','TN_InvalidBrand','Bitte wählen Sie eine Marke aus der Liste.'),
 ('EN','TN_InvalidWeek','Please choose a week from the list.'),
 ('DE','TN_InvalidWeek','Bitte wählen Sie eine Woche aus der Liste.'),
 ('EN','TN_EmailValidationAutoReport','Please enter a valid e-mail address.'),
 ('DE','TN_EmailValidationAutoReport','Bitte tragen Sie eine gültige E-Mail-Adresse ein.');

DELETE t FROM Translation.dbo.Translation t
JOIN @tk k ON k.LanguageCode = t.LanguageCode AND k.TranslationKey = t.TranslationKey;

INSERT INTO Translation.dbo.Translation (LanguageCode, TranslationKey, Value, IsPublic)
SELECT LanguageCode, TranslationKey, Value, 0 FROM @tk;

COMMIT TRANSACTION;
GO


/* =====================================================================
   PART A – DDL (ReportDB)
   ===================================================================== */
USE ReportDB;
GO

IF OBJECT_ID('control.T_Control_Autoreport_Weeks','U') IS NULL
CREATE TABLE control.T_Control_Autoreport_Weeks (
    id         int IDENTITY(1,1) NOT NULL CONSTRAINT PK_Autoreport_Weeks PRIMARY KEY,
    week_type  varchar(20)  NOT NULL CONSTRAINT CK_Autoreport_Weeks_Type CHECK (week_type IN ('report','comparison')),
    week_value nvarchar(15) NOT NULL,
    IsDeleted  bit          NOT NULL CONSTRAINT DF_Autoreport_Weeks_IsDeleted DEFAULT 0,
    CONSTRAINT UQ_Autoreport_Weeks UNIQUE (week_type, week_value)
);
GO

-- Seed: adjust format/values as needed (your existing row uses '48/25', earlier scripts '48/2026')
INSERT INTO control.T_Control_Autoreport_Weeks (week_type, week_value)
SELECT v.t, v.w
FROM (VALUES ('report','47/2026'),('report','48/2026'),('report','49/2026'),
             ('comparison','46/2026'),('comparison','47/2026'),('comparison','48/2026')) v(t, w)
WHERE NOT EXISTS (SELECT 1 FROM control.T_Control_Autoreport_Weeks x
                  WHERE x.week_type = v.t AND x.week_value = v.w);
GO

CREATE OR ALTER VIEW dbo.V_Autoreport_DropdownValues
AS
SELECT CAST(b.brand_name AS nvarchar(200)) AS brand_name,
       CAST(NULL AS nvarchar(15))          AS report_week,
       CAST(NULL AS nvarchar(15))          AS comparison_week,
       CAST(0 AS bit)                      AS IsDeleted
FROM control.T_Control_Autoreport_Brands b
WHERE b.is_active = 1
UNION ALL
SELECT NULL, w.week_value, NULL, w.IsDeleted
FROM control.T_Control_Autoreport_Weeks w
WHERE w.week_type = 'report'
UNION ALL
SELECT NULL, NULL, w.week_value, w.IsDeleted
FROM control.T_Control_Autoreport_Weeks w
WHERE w.week_type = 'comparison';
GO

/* =====================================================================
   PART B – Report config (one transaction)
   ===================================================================== */
USE ReportDB;
GO
SET XACT_ABORT ON;
BEGIN TRAN;

SET IDENTITY_INSERT dbo.T_CONTROL_Report_DataSource ON;
INSERT INTO dbo.T_CONTROL_Report_DataSource (ReportDataSourceID, DataSource, ReportID)
VALUES (9502, 'V_Autoreport_DropdownValues', 950);
SET IDENTITY_INSERT dbo.T_CONTROL_Report_DataSource OFF;

SET IDENTITY_INSERT dbo.T_CONTROL_Report_DataSourceColumns ON;
INSERT INTO dbo.T_CONTROL_Report_DataSourceColumns
 (ReportDataSourceColumnsID,ColumnName,DataType,Displayed,Sortable,Filterable,ColumnNameTranslationKey,
  LineBreak,ColumnStyle,NumberLocaleFormat,CurrencyTK,Editable,ReportDataSourceID,DisplayOrder,
  ColorCoded,OrderBy,OrderParameter,IsPrimaryKey)
VALUES
 (950201,'brand_name',     'string',0,0,0,'TN_Brand',          NULL,NULL,NULL,NULL,0,9502,1,NULL,0,NULL,NULL),
 (950202,'report_week',    'string',0,0,0,'TN_Berichtswoche',  NULL,NULL,NULL,NULL,0,9502,2,NULL,0,NULL,NULL),
 (950203,'comparison_week','string',0,0,0,'TN_Abgleichswoche', NULL,NULL,NULL,NULL,0,9502,3,NULL,0,NULL,NULL);
SET IDENTITY_INSERT dbo.T_CONTROL_Report_DataSourceColumns OFF;

-- Turn the 3 editable columns into dropdowns linked to the list columns
UPDATE dbo.T_CONTROL_Report_DataSourceColumns
SET DataType = 'dropdown',
    ValueSourceColumnId = CASE ReportDataSourceColumnsID
                            WHEN 950102 THEN 950201
                            WHEN 950103 THEN 950202
                            WHEN 950104 THEN 950203 END
WHERE ReportDataSourceColumnsID IN (950102, 950103, 950104);

-- Regex no longer needed (the dropdown validates against the list itself); keep "required"
DELETE FROM dbo.T_CONTROL_Report_DataSourceColumnsValidation
WHERE ReportDataSourceColumnsID IN (950102, 950103, 950104)
  AND ValidationMappingID = 2;

COMMIT;
GO

/* =====================================================================
   PART C – Translation (DE missing for TN_InvalidSelection)
   ===================================================================== */
USE Translation;
GO
IF NOT EXISTS (SELECT 1 FROM dbo.Translation WHERE TranslationKey = 'TN_InvalidSelection' AND LanguageCode = 'DE')
    INSERT INTO dbo.Translation (LanguageCode, TranslationKey, Value, IsPublic)
    VALUES ('DE', 'TN_InvalidSelection', 'Ungültige Auswahl', 0);
GO

/* =====================================================================
   PART D – Verify (same query the backend runs)
   ===================================================================== */
USE ReportDB;
GO
SELECT ReportDataSourceColumnsID, ColumnName, DataType, ValueSourceColumnId
FROM dbo.T_CONTROL_Report_DataSourceColumns
WHERE ReportDataSourceID IN (9501, 9502)
ORDER BY ReportDataSourceColumnsID;

SELECT DISTINCT brand_name      FROM V_Autoreport_DropdownValues WHERE brand_name      IS NOT NULL AND IsDeleted = 0;
SELECT DISTINCT report_week     FROM V_Autoreport_DropdownValues WHERE report_week     IS NOT NULL AND IsDeleted = 0;
SELECT DISTINCT comparison_week FROM V_Autoreport_DropdownValues WHERE comparison_week IS NOT NULL AND IsDeleted = 0;