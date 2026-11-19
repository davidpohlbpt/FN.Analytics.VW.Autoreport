-- Frontend "Auto Report Einstellungen" (Report 950): UI-Anpassungen. SQL Server, idempotent.
-- Der Endzustand steht auch in 000_Frontend_Aufbau.sql (fuer einen Neuaufbau); dieses Skript
-- bringt eine bestehende Umgebung auf denselben Stand.
--
--   - Variantenmanagement (inkl. "Variante auswaehlen") entfernt   TileOption 9  HasVariantManagement
--   - Excel-Export entfernt                                       TileOption 8  HasExcelExport
--                                                                 TileOption 12 ExcelTableHeaderType
--   - Spalte last_report_time: "Letzter Report" -> "Letzte Anforderung"
--   - Spalte send_now ("Auswertung anfordern"): Haken bzw. leeres Kaestchen statt true/false
--
-- Ohne Eintrag gilt der Default aus T_CONTROL_TileType_Option (fuer 8 und 9: '0' = aus).
-- Nach dem Ausfuehren die Seite im Browser neu laden (das Frontend cached die Konfiguration).

SET XACT_ABORT ON;
BEGIN TRANSACTION;

DELETE FROM ReportDB.dbo.T_CONTROL_Layout_TileOption
WHERE TileID = 9502 AND OptionID IN (8, 9, 12);

INSERT INTO ReportDB.dbo.T_CONTROL_Report_DataSourceColumnsFormatting
    (Style, Icon, Value, MappingType, ReportDataSourceColumnsID)
SELECT v.Style, v.Icon, v.Value, 'Equal', 950105
FROM (VALUES ('color:black', 'fa fa-check',    '1'),
             ('color:black', 'fa fa-square-o', '0')) v(Style, Icon, Value)
WHERE NOT EXISTS (SELECT 1 FROM ReportDB.dbo.T_CONTROL_Report_DataSourceColumnsFormatting f
                  WHERE f.ReportDataSourceColumnsID = 950105 AND f.Value = v.Value);

DECLARE @tk TABLE (LanguageCode nvarchar(5), TranslationKey nvarchar(200), Value nvarchar(max));
INSERT INTO @tk VALUES
 ('EN', 'TN_LastReportTime', 'Last request'),
 ('DE', 'TN_LastReportTime', 'Letzte Anforderung');

DELETE t FROM Translation.dbo.Translation t
JOIN @tk k ON k.LanguageCode = t.LanguageCode AND k.TranslationKey = t.TranslationKey;

INSERT INTO Translation.dbo.Translation (LanguageCode, TranslationKey, Value, IsPublic)
SELECT LanguageCode, TranslationKey, Value, 0 FROM @tk;

COMMIT TRANSACTION;
GO

-- Kontrolle
SELECT OptionID, Value FROM ReportDB.dbo.T_CONTROL_Layout_TileOption WHERE TileID = 9502 ORDER BY OptionID;
SELECT LanguageCode, Value FROM Translation.dbo.Translation WHERE TranslationKey = 'TN_LastReportTime';
SELECT Value, Icon, Style FROM ReportDB.dbo.T_CONTROL_Report_DataSourceColumnsFormatting WHERE ReportDataSourceColumnsID = 950105;
