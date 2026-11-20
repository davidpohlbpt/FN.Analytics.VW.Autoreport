-- Frontend column last_report_time is now set by vw-autoreport-sendemail after a
-- successful send (German local time), so the label is renamed. Idempotent.

DECLARE @tk TABLE (LanguageCode nvarchar(5), TranslationKey nvarchar(200), Value nvarchar(max));
INSERT INTO @tk VALUES
 ('EN', 'TN_LastReportTime', 'Last sent'),
 ('DE', 'TN_LastReportTime', 'Letzter Versand');

DELETE t FROM Translation.dbo.Translation t
JOIN @tk k ON k.LanguageCode = t.LanguageCode AND k.TranslationKey = t.TranslationKey;

INSERT INTO Translation.dbo.Translation (LanguageCode, TranslationKey, Value, IsPublic)
SELECT LanguageCode, TranslationKey, Value, 0 FROM @tk;
GO

-- After running, reload the frontend page (the frontend caches its configuration).
SELECT LanguageCode, Value FROM Translation.dbo.Translation WHERE TranslationKey = 'TN_LastReportTime';
