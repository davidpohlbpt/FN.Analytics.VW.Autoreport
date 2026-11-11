-- Seed: one template with six KPIs. KPI 1 carries the real texts/palette from the VW
-- template; KPIs 2-6 are placeholders on the stub source until their definitions and
-- sources (frontend chart ids or backend query) are known.
-- Adjust the S3 bucket name before running.

DECLARE @template_id INT;

INSERT INTO control.T_Control_Autoreport_Templates
    (name, template_link, language, target_file_name, target_location, default_reference_weeks_back, email_subject, is_active)
VALUES
    (N'VW KPI Weekly',
     N's3://<bucket>/templates/VW_Template_Overview.pptx',
     N'DE',
     N'VW_KPI_Report_{brand}_{current}_vs_{reference}',
     N's3://<bucket>/reports',
     8,
     N'VW KPI Report {brand}: {current} vs. {reference}',
     1);
SET @template_id = SCOPE_IDENTITY();

DECLARE @age_palette NVARCHAR(2000) = N'{"< 1 Jahr": "rgb(146, 208, 80)", "1-2 Jahre": "rgb(197, 224, 180)", "2 - 4 Jahre": "rgb(255, 230, 153)", "4 - 6 Jahre": "rgb(244, 177, 131)", "> 6 Jahre": "rgb(255, 0, 0)", "ohne Daten": "rgb(127, 127, 127)"}';
DECLARE @status_palette NVARCHAR(2000) = N'{"erfüllt": "rgb(146, 208, 80)", "teilweise erfüllt": "rgb(255, 230, 153)", "nicht erfüllt": "rgb(255, 0, 0)", "ohne Daten": "rgb(127, 127, 127)"}';

INSERT INTO control.T_Control_Autoreport_Mappings
    (template_id, kpi_key, kpi_order, kpi_name, slide_title, slide_subtitle, source, query_key, palette_json, average_label)
VALUES
    (@template_id, N'bka_age', 1, N'BKA Alter', N'BKAs nach Aktualisierung',
     N'Wann wurden BKAs das letzte Mal bearbeitet und wie ist das durchschnittliche BKA Alter?',
     N'stub', N'default', @age_palette, N'Ø'),
    (@template_id, N'kpi2', 2, N'KPI 2', N'KPI 2 (Platzhalter)', N'Platzhalter-Untertitel KPI 2', N'stub', N'default', @age_palette, N'Ø'),
    (@template_id, N'kpi3', 3, N'KPI 3', N'KPI 3 (Platzhalter)', N'Platzhalter-Untertitel KPI 3', N'stub', N'default', @status_palette, NULL),
    (@template_id, N'kpi4', 4, N'KPI 4', N'KPI 4 (Platzhalter)', N'Platzhalter-Untertitel KPI 4', N'stub', N'default', @age_palette, N'Ø'),
    (@template_id, N'kpi5', 5, N'KPI 5', N'KPI 5 (Platzhalter)', N'Platzhalter-Untertitel KPI 5', N'stub', N'default', @status_palette, NULL),
    (@template_id, N'kpi6', 6, N'KPI 6', N'KPI 6 (Platzhalter)', N'Platzhalter-Untertitel KPI 6', N'stub', N'default', @age_palette, N'Ø');

-- Example recipients
INSERT INTO control.T_Control_Autoreport_Recipients (template_id, email, brand, reference_timestamp, send_now, is_active, last_edited_at)
VALUES
    (@template_id, N'you@example.com', N'Audi', N'KW37', 0, 1, SYSUTCDATETIME()),
    (@template_id, N'you@example.com', N'Seat', NULL,    0, 1, SYSUTCDATETIME());
GO
