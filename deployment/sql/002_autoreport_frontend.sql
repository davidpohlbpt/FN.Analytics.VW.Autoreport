-- Frontend setup for the AutoReport recipient editor.
-- Prerequisite: 001_autoreport_core.sql has completed successfully.
-- Run once on PROD after confirming the reserved IDs below are unused.

USE ReportDB;
GO

IF DB_ID(N'IdentityServer') IS NULL OR DB_ID(N'Translation') IS NULL
    THROW 50100, 'IdentityServer and Translation databases must be available on this SQL Server instance.', 1;
IF OBJECT_ID(N'dbo.T_CONTROL_Report', N'U') IS NULL
   OR OBJECT_ID(N'dbo.T_CONTROL_Report_DataSource', N'U') IS NULL
   OR OBJECT_ID(N'dbo.T_CONTROL_Report_DataSourceColumns', N'U') IS NULL
   OR OBJECT_ID(N'dbo.T_CONTROL_Layout_Tiles', N'U') IS NULL
   OR OBJECT_ID(N'dbo.T_CONTROL_Layout_Table', N'U') IS NULL
   OR OBJECT_ID(N'dbo.T_CONTROL_Layout_Text', N'U') IS NULL
   OR OBJECT_ID(N'dbo.T_CONTROL_Layout_TileOption', N'U') IS NULL
   OR OBJECT_ID(N'dbo.T_CONTROL_Report_DataSourceColumnsValidation', N'U') IS NULL
   OR OBJECT_ID(N'dbo.T_CONTROL_Report_DataSourceColumnsFormatting', N'U') IS NULL
    THROW 50101, 'ReportDB frontend configuration tables are missing.', 1;
IF NOT EXISTS (
       SELECT 1 FROM IdentityServer.sys.tables t
       JOIN IdentityServer.sys.schemas s ON s.schema_id = t.schema_id
       WHERE s.name = N'dbo' AND t.name = N'T_CONTROL_GenericHeaderBar'
   )
   OR NOT EXISTS (
       SELECT 1 FROM IdentityServer.sys.tables t
       JOIN IdentityServer.sys.schemas s ON s.schema_id = t.schema_id
       WHERE s.name = N'dbo' AND t.name = N'T_CONTROL_HeaderBarFunctionality'
   )
   OR NOT EXISTS (
       SELECT 1 FROM IdentityServer.sys.tables t
       JOIN IdentityServer.sys.schemas s ON s.schema_id = t.schema_id
       WHERE s.name = N'dbo' AND t.name = N'MenuItem'
   )
   OR NOT EXISTS (
       SELECT 1 FROM Translation.sys.tables t
       JOIN Translation.sys.schemas s ON s.schema_id = t.schema_id
       WHERE s.name = N'dbo' AND t.name = N'Translation'
   )
    THROW 50102, 'IdentityServer or Translation prerequisite tables are missing.', 1;

IF EXISTS (SELECT 1 FROM IdentityServer.dbo.T_CONTROL_GenericHeaderBar WHERE HeaderBarID = 950)
   OR EXISTS (SELECT 1 FROM IdentityServer.dbo.T_CONTROL_HeaderBarFunctionality WHERE HeaderBarFunctionalityID = 95001)
   OR EXISTS (SELECT 1 FROM IdentityServer.dbo.MenuItem WHERE MenuItemID = 950)
   OR EXISTS (SELECT 1 FROM dbo.T_CONTROL_Report WHERE ReportID = 950)
   OR EXISTS (SELECT 1 FROM dbo.T_CONTROL_Report_DataSource WHERE ReportDataSourceID IN (9501,9502))
   OR EXISTS (SELECT 1 FROM dbo.T_CONTROL_Report_DataSourceColumns WHERE ReportDataSourceColumnsID BETWEEN 950100 AND 950204)
   OR EXISTS (SELECT 1 FROM dbo.T_CONTROL_Layout_Tiles WHERE TileID IN (9501,9502))
   OR EXISTS (SELECT 1 FROM dbo.T_CONTROL_Layout_Table WHERE TableID = 9501)
   OR EXISTS (SELECT 1 FROM dbo.T_CONTROL_Layout_Text WHERE TextId = 9501)
    THROW 50103, 'One or more reserved AutoReport frontend IDs are already in use; reconcile before deployment.', 1;

SET XACT_ABORT ON;
BEGIN TRANSACTION;

SET IDENTITY_INSERT IdentityServer.dbo.T_CONTROL_GenericHeaderBar ON;
INSERT INTO IdentityServer.dbo.T_CONTROL_GenericHeaderBar
    (HeaderBarID, Report, PageURLEnding, HeaderTranslationKey, TimestampConfigurationID, ScenID)
VALUES (950, N'AutoReportRecipients_Main', N'GenericReport',
        N'TN_AutoReportRecipients_Main_Titel', NULL, NULL);
SET IDENTITY_INSERT IdentityServer.dbo.T_CONTROL_GenericHeaderBar OFF;

SET IDENTITY_INSERT IdentityServer.dbo.T_CONTROL_HeaderBarFunctionality ON;
INSERT INTO IdentityServer.dbo.T_CONTROL_HeaderBarFunctionality
    (HeaderBarFunctionalityID, HeaderBarID, Functionality, Level, [Order])
VALUES (95001, 950, N'Logout', 0, 1);
SET IDENTITY_INSERT IdentityServer.dbo.T_CONTROL_HeaderBarFunctionality OFF;

SET IDENTITY_INSERT IdentityServer.dbo.MenuItem ON;
INSERT INTO IdentityServer.dbo.MenuItem
    (MenuItemID, MenuItemName, TranslationKey, URL, Permission, IsGeneric,
     Display, DisplayOrder, HeaderBarID, MenuCategoryID, ConfidentialityId)
VALUES (950, N'AutoReportRecipients_Main', N'TN_AutoReportRecipients_Main_Titel',
        N'/data-quality/genericreport', N'AutoReportRecipientsClaim', 1,
        1, 2, 950, 24, 3);
SET IDENTITY_INSERT IdentityServer.dbo.MenuItem OFF;

SET IDENTITY_INSERT dbo.T_CONTROL_Report ON;
INSERT INTO dbo.T_CONTROL_Report
    (ReportID, ReportName, MenuItemID, MeasurementUnitRemWorkID, HasMask, HasNestedFilter,
     UnionFilteringType, ShouldIgnoreDefaultReportingUnit, LazyLoading)
VALUES (950, N'AutoReportRecipients_Main', 950, 1, NULL, NULL, NULL, 1, 1);
SET IDENTITY_INSERT dbo.T_CONTROL_Report OFF;

SET IDENTITY_INSERT dbo.T_CONTROL_Report_DataSource ON;
INSERT INTO dbo.T_CONTROL_Report_DataSource (ReportDataSourceID, DataSource, ReportID)
VALUES (9501, N'V_Autoreport_Recipients', 950),
       (9502, N'V_Autoreport_DropdownValues', 950);
SET IDENTITY_INSERT dbo.T_CONTROL_Report_DataSource OFF;

SET IDENTITY_INSERT dbo.T_CONTROL_Report_DataSourceColumns ON;
INSERT INTO dbo.T_CONTROL_Report_DataSourceColumns
    (ReportDataSourceColumnsID, ColumnName, DataType, Displayed, Sortable, Filterable,
     ColumnNameTranslationKey, LineBreak, ColumnStyle, NumberLocaleFormat, CurrencyTK,
     Editable, ReportDataSourceID, DisplayOrder, ColorCoded, OrderBy, OrderParameter,
     IsPrimaryKey, ValueSourceColumnId)
VALUES
    (950100, N'RowID',             N'numeric',   0, 1, 1, N'RowId',              NULL, NULL, NULL, NULL, 0, 9501, 0, NULL, 0, NULL, 1, NULL),
    (950101, N'email',             N'string',    1, 1, 1, N'TN_Email',           NULL, NULL, NULL, NULL, 1, 9501, 1, NULL, 1, N'ASC', NULL, NULL),
    (950102, N'brand_name',        N'string',  1, 1, 1, N'TN_Brand',           NULL, NULL, NULL, NULL, 1, 9501, 2, NULL, 0, NULL, NULL, 950201),
    (950103, N'report_week',       N'string',  1, 1, 1, N'TN_Berichtswoche',   NULL, NULL, NULL, NULL, 1, 9501, 3, NULL, 0, NULL, NULL, 950202),
    (950104, N'comparison_week',   N'string',  1, 1, 1, N'TN_Abgleichswoche',  NULL, NULL, NULL, NULL, 1, 9501, 4, NULL, 0, NULL, NULL, 950203),
    (950105, N'send_now',          N'boolean',   1, 1, 1, N'TN_SendNow',         NULL, NULL, NULL, NULL, 1, 9501, 5, NULL, 0, NULL, NULL, NULL),
    (950106, N'last_report_time',  N'datetime',  1, 1, 1, N'TN_LastReportTime',  NULL, NULL, NULL, NULL, 0, 9501, 6, NULL, 0, NULL, NULL, NULL),
    (950201, N'brand_name',        N'string',    0, 1, 0, N'TN_Brand',           NULL, NULL, NULL, NULL, 0, 9502, 1, NULL, 1, N'ASC', NULL, NULL),
    (950202, N'report_week',       N'string',    0, 0, 0, N'TN_Berichtswoche',   NULL, NULL, NULL, NULL, 0, 9502, 2, NULL, 0, NULL, NULL, NULL),
    (950203, N'comparison_week',   N'string',    0, 0, 0, N'TN_Abgleichswoche',  NULL, NULL, NULL, NULL, 0, 9502, 3, NULL, 0, NULL, NULL, NULL),
    (950204, N'sort_date',         N'date',      0, 0, 0, NULL,                  NULL, NULL, NULL, NULL, 0, 9502, 4, NULL, 0, NULL, NULL, NULL);
SET IDENTITY_INSERT dbo.T_CONTROL_Report_DataSourceColumns OFF;

INSERT INTO dbo.T_CONTROL_Report_DataSourceColumnsValidation
    (ReportDataSourceColumnsID, Mandatory, ValidationMappingID, ValidationValue, ErrorTranslationKey)
VALUES
    (950101, 1, 3, NULL, N'TN_ValueRequired'),
    (950101, 1, 2, N'^[^@\s]+@[^@\s]+\.[^@\s]+$', N'TN_EmailValidationAutoReport'),
    (950102, 1, 3, NULL, N'TN_ValueRequired'),
    (950103, 1, 3, NULL, N'TN_ValueRequired'),
    (950104, 1, 3, NULL, N'TN_ValueRequired');

INSERT INTO dbo.T_CONTROL_Report_DataSourceColumnsFormatting
    (Style, Icon, Value, MappingType, ReportDataSourceColumnsID)
VALUES
    (N'color:black', N'fa fa-check',    N'1', N'Equal', 950105),
    (N'color:black', N'fa fa-square-o', N'0', N'Equal', 950105);

SET IDENTITY_INSERT dbo.T_CONTROL_Layout_Tiles ON;
INSERT INTO dbo.T_CONTROL_Layout_Tiles
    (TileID, TileName, [Order], Display, TitleTK, HelpTextTK, GridHeight,
     HelperTitleTK, HelperTitleUnitTK, ReportID, ReportDataSourceID, TileTypeID)
VALUES
    (9501, N'AutoReportRecipients_Main_Info', 1, 1, N'TN_AutoReportRecipients_Main_Info_Titel',
     NULL, N'grid-item-heavier', NULL, NULL, 950, NULL, 7),
    (9502, N'AutoReportRecipients_Main_Table', 2, 1, N'TN_AutoReportRecipients_Main_Table_Titel',
     N'TN_Helptext_AutoReportRecipients_Main_Table', N'grid-item-tallest', NULL, NULL, 950, 9501, 2);
SET IDENTITY_INSERT dbo.T_CONTROL_Layout_Tiles OFF;

SET IDENTITY_INSERT dbo.T_CONTROL_Layout_Text ON;
INSERT INTO dbo.T_CONTROL_Layout_Text (TextId, TileID, Content)
VALUES (9501, 9501, N'TN_AutoReportRecipients_Info
<div align="left"><img alt="Not Found" src="https://volkswagen-net.de/wikis/download/attachments/2755133687/VW_autoreport_tutorial_DE.png?version=1&modificationDate=1795439797000&api=v2" width="75%" height="75%">
<p><br></p>
TN_AutoReportRecipients_Explanation');
SET IDENTITY_INSERT dbo.T_CONTROL_Layout_Text OFF;

SET IDENTITY_INSERT dbo.T_CONTROL_Layout_Table ON;
INSERT INTO dbo.T_CONTROL_Layout_Table
    (TableID, ReportID, HasCheckbox, NoRowsCheckedTranslationKey, RowsCheckedTranslationKey,
     ColumnToAllowSelection, HasPagination, SelectionIcon, ReportDataSourceID,
     HasAuditing, HasColumnFilter, HasColumnFilterDynamicWidth, TileID)
VALUES (9501, 950, 0, NULL, NULL, NULL, 1, NULL, 9501, 0, 1, 1, 9502);
SET IDENTITY_INSERT dbo.T_CONTROL_Layout_Table OFF;

INSERT INTO dbo.T_CONTROL_Layout_TileOption (TileID, OptionID, Value)
VALUES (9502, 7, N'1'),
       (9502, 17, N'ConfirmationDialogDelete'),
       (9502, 28, N'AutoReportRecipientsClaim'),
       (9502, 29, N'AutoReportRecipientsClaim'),
       (9502, 30, N'AutoReportRecipientsClaim');

DECLARE @tk TABLE (
    LanguageCode NVARCHAR(5),
    TranslationKey NVARCHAR(200),
    Value NVARCHAR(MAX)
);
INSERT INTO @tk (LanguageCode, TranslationKey, Value)
VALUES
    (N'EN', N'TN_AutoReportRecipients_Main_Titel', N'Auto Report Settings'),
    (N'DE', N'TN_AutoReportRecipients_Main_Titel', N'Auto Report Einstellungen'),
    (N'EN', N'TN_AutoReportRecipients_Main_Info_Titel', N'Information'),
    (N'DE', N'TN_AutoReportRecipients_Main_Info_Titel', N'Information'),
    (N'EN', N'TN_AutoReportRecipients_Main_Table_Titel', N'Autoreport Configuration'),
    (N'DE', N'TN_AutoReportRecipients_Main_Table_Titel', N'Autoreport-Konfiguration'),
    (N'EN', N'TN_Helptext_AutoReportRecipients_Main_Table', N'Brand, reporting week and comparison week must be chosen from the allowed values.'),
    (N'DE', N'TN_Helptext_AutoReportRecipients_Main_Table', N'Marke, Berichtswoche und Vergleichswoche müssen aus den erlaubten Werten gewählt werden.'),
    (N'EN', N'TN_AutoReportRecipients_Main_Info', N'<p><br></p>
<big>
<p>In this table, you can specify the recipients to whom the Data Quality Report will be sent. Each user can configure their own Control Center Report and select the desired purchasing organization as well as the reporting and comparison week. If you activate “Request Report”, the report will be sent by email within five minutes.</p>
<br>
<p><strong>You can add or modify entries using the “Edit” button. Please only edit your own entries.</strong></p>
<br>
<p>The “Last Sent” column is filled automatically. Please leave this field empty when adding a new recipient.</p>
</big>
<p><br></p>
<h3><br></h3>'),
    (N'DE', N'TN_AutoReportRecipients_Main_Info', N'<p><br></p>
<big>
<p>In dieser Tabelle legen Sie fest, an welche Empfänger der Datenqualitätsbericht gesendet wird. Jeder Nutzer kann einen eigenen Control-Center-Bericht konfigurieren und die gewünschte Einkaufsorganisation sowie die Berichts- und Vergleichswoche auswählen. Wenn Sie „Auswertung anfordern“ aktivieren, wird der Bericht innerhalb von fünf Minuten per E-Mail versendet.</p>
<br>
<p><strong>Über die Schaltfläche „Bearbeiten“ können Sie Einträge hinzufügen oder ändern. Bitte bearbeiten Sie nur Ihre eigenen Einträge.</strong> Prüfen Sie zunächst über die Suchleiste in der Spalte „E-Mail“, ob die betreffende E-Mail-Adresse bereits vorhanden ist. Falls ja, ändern Sie bitte den bestehenden Eintrag, statt einen neuen anzulegen.</p>
<br>
<p>Die Spalte „Letzter Versand“ wird automatisch befüllt. Lassen Sie dieses Feld beim Anlegen eines Empfängers leer.</p>

</big>
<p><br></p>
<h3><br></h3>'),
    (N'EN', N'TN_Brand', N'Purchasing organization'),
    (N'DE', N'TN_Brand', N'Einkaufsorganisation'),
    (N'EN', N'TN_Berichtswoche', N'Reporting week'),
    (N'DE', N'TN_Berichtswoche', N'Berichtswoche'),
    (N'EN', N'TN_Abgleichswoche', N'Comparison week'),
    (N'DE', N'TN_Abgleichswoche', N'Vergleichswoche'),
    (N'EN', N'TN_SendNow', N'Send report'),
    (N'DE', N'TN_SendNow', N'Auswertung anfordern'),
    (N'EN', N'TN_LastReportTime', N'Last sent'),
    (N'DE', N'TN_LastReportTime', N'Letzter Versand'),
    (N'EN', N'TN_InvalidBrand', N'Please choose a brand from the list.'),
    (N'DE', N'TN_InvalidBrand', N'Bitte wählen Sie eine Marke aus der Liste.'),
    (N'EN', N'TN_InvalidWeek', N'Please choose a week from the list.'),
    (N'DE', N'TN_InvalidWeek', N'Bitte wählen Sie eine Woche aus der Liste.'),
    (N'EN', N'TN_EmailValidationAutoReport', N'Please enter a valid e-mail address.'),
    (N'DE', N'TN_EmailValidationAutoReport', N'Bitte tragen Sie eine gültige E-Mail-Adresse ein.'),
    (N'EN', N'TN_AutoReportRecipients_Explanation', N'<p><strong>Step 1:</strong> Switch to edit mode.</p>

<p><strong>Step 2:</strong> To add a new entry, click the plus icon in the top-right corner. Enter your email address and select the purchasing organization, reporting week, and comparison week from the dropdown menus. Then select the <strong>“Send report”</strong> checkbox to request the report by email.</p>

<p>To edit an existing entry, double-click the relevant row. Save your changes by double-clicking the <strong>“Save”</strong> button.</p>

<p><strong>Step 3:</strong> Check that your entry matches the example and that <strong>“Send report”</strong> is selected. After you save, the report is usually sent by email within about five minutes. Once it has been sent, the checkbox is cleared automatically. To request another report, simply select it again. If you don’t receive an email, check your details and contact us if needed.</p>'),
    (N'DE', N'TN_AutoReportRecipients_Explanation', N'<p><strong>Schritt 1:</strong> Wechseln Sie in den Editier modus.</p>

<p><strong>Schritt 2:</strong> Um einen neuen Eintrag anzulegen, klicken Sie oben rechts auf das Plus-Symbol. Geben Sie Ihre E-Mail-Adresse ein und wählen Sie die Einkaufsorganisation sowie die Berichts- und Vergleichswoche über die Dropdown-Menüs aus. Klicken Sie anschließend das Kästchen <strong>„Auswertung anfordern“</strong>, damit der Report erstellt und per E-Mail versendet wird.</p>

<p>Um einen bestehenden Eintrag zu ändern, doppelklicken Sie auf die entsprechende Zeile. Speichern Sie Ihre Änderungen mit einem Doppelklick auf die Schaltfläche <strong>„Speichern“</strong>.</p>

<p><strong>Schritt 3:</strong> Prüfen Sie, ob Ihr Eintrag wie im Beispiel aussieht und das Kontrollkästchen <strong>„Auswertung anfordern“</strong> aktiviert ist. Nach dem Speichern wird der Report in der Regel innerhalb von etwa fünf Minuten per E-Mail versendet. Nachdem der Report gesendet wird, wird der Haken von „Auswertung anfordern“ entfernt. Bei erneuter Anfrage können Sie einfach wieder den Haken setzen.Falls Sie keine E-Mail erhalten, prüfen Sie Ihre Angaben und wenden Sie sich bei Bedarf an uns.</p>'),
    (N'EN', N'TN_InvalidSelection', N'Invalid selection'),
    (N'DE', N'TN_InvalidSelection', N'Ungültige Auswahl');

DELETE t
FROM Translation.dbo.Translation t
JOIN @tk k ON k.LanguageCode = t.LanguageCode AND k.TranslationKey = t.TranslationKey;

INSERT INTO Translation.dbo.Translation (LanguageCode, TranslationKey, Value, IsPublic)
SELECT LanguageCode, TranslationKey, Value, 0 FROM @tk;

COMMIT TRANSACTION;
GO

-- Run after creating the report and before opening the page in the frontend.
SELECT ReportDataSourceColumnsID, ColumnName, DataType, ValueSourceColumnId, OrderBy, OrderParameter
FROM dbo.T_CONTROL_Report_DataSourceColumns
WHERE ReportDataSourceID IN (9501, 9502)
ORDER BY ReportDataSourceColumnsID;
GO
