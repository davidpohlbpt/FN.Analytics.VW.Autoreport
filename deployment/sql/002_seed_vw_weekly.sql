-- Seed: one template with the six IDM Control Center KPIs (ReportDB report/menu item 1200).
-- source = 'leitstand': labels, colours and slice order are read live from the Control
-- Center chart configuration (T_Chart_*), numbers from dbo.T_RESULT_Leitstand_Overview
-- (MOD = 'Alle', EK_ORG = brand). palette_json is left NULL on purpose.
-- Adjust the S3 bucket name before running.

DECLARE @template_id INT;

INSERT INTO control.T_Control_Autoreport_Templates
    (name, template_link, language, target_file_name, target_location, email_subject, is_active)
VALUES
    (N'IDM Control Center Weekly',
     N's3://<bucket>/templates/VW_Template_Overview.pptx',
     N'DE',
     N'IDM_Control_Center_{brand}_{current}_vs_{reference}',
     N's3://<bucket>/reports',
     N'IDM Control Center {brand}: {current} vs. {reference}',
     1);
SET @template_id = SCOPE_IDENTITY();

INSERT INTO control.T_Control_Autoreport_Mappings
    (template_id, kpi_key, kpi_order, kpi_name, slide_title, slide_subtitle, source,
     menu_item_id, report_id, tile_id, chart_id, palette_json, average_label)
VALUES
    (@template_id, N'bka_aktualisierung',       1, N'BKA nach Aktualisierung',      N'BKA nach Aktualisierung',
     N'Wann wurden BKAs das letzte Mal bearbeitet und wie ist das durchschnittliche BKA Alter?',
     N'leitstand', 1200, 1200, 12000,  12000,  NULL, N'Ø'),
    (@template_id, N'bka_bearbeitungsstatus',   2, N'BKA nach Bearbeitungsstatus',  N'BKA nach Bearbeitungsstatus',
     N'In welchem Handlungsfeld befinden sich die BKAs aktuell?',
     N'leitstand', 1200, 1200, 12002,  12002,  NULL, NULL),
    (@template_id, N'uvb_fehlercode',           3, N'UVB Fehler nach Fehlercode',   N'UVB Fehler nach Fehlercode',
     N'Welche UVB Fehler enthalten die BKAs?',
     N'leitstand', 1200, 1200, 12004,  12004,  NULL, NULL),
    (@template_id, N'rote_bka',                 4, N'Rote BKAs',                    N'Rote BKAs',
     N'Wie lange übersteigt der Bedarf die Maximalkapazität?',
     N'leitstand', 1200, 1200, 12006,  12006,  NULL, NULL),
    (@template_id, N'bka_abgleichstatus',       5, N'BKA nach Abgleichstatus',      N'BKA nach Abgleichstatus',
     N'Wie ist die Versorgungssituation laut Bedarfs-Kapazitäts-Abgleich?',
     N'leitstand', 1200, 1200, 120013, 120013, NULL, NULL),
    (@template_id, N'kapazitaet_saisonalitaet', 6, N'Saisonalität von Kapazitäten', N'Saisonalität von Kapazitäten',
     N'Wie viele unterschiedliche Kapazitätseinträge haben die BKAs?',
     N'leitstand', 1200, 1200, 120017, 120017, NULL, NULL);

-- Brands: filter_value = EK_ORG value in dbo.T_RESULT_Leitstand_Overview.
-- Check the list with: SELECT DISTINCT EK_ORG FROM dbo.T_RESULT_Leitstand_Overview
INSERT INTO control.T_Control_Autoreport_Brands (brand_name, filter_value, is_active)
VALUES
    (N'Volkswagen PKW', N'VW PKW',        1),
    (N'Audi',           N'Audi',          1),
    (N'Audi Hungaria',  N'Audi Hungaria', 1),
    (N'SEAT',           N'SEAT',          1),
    (N'Skoda',          N'Skoda',         1),
    (N'Porsche',        N'Porsche',       1),
    (N'MAN',            N'MAN',           1);

-- Example recipients; the reference week is mandatory. Week 1 of the current year is
-- the suggested frontend default; the test system only has data up to 2025-11-28,
-- so the examples use 2025 weeks.
INSERT INTO control.T_Control_Autoreport_Recipients
    (template_id, email, brand_id, reference_year, reference_week, send_now, is_active, last_edited_at)
SELECT @template_id, N'you@example.com', b.id, r.y, r.w, 0, 1, SYSUTCDATETIME()
FROM (VALUES (N'VW PKW', 2025, 39), (N'VW PKW', 2025, 30), (N'Audi', 2025, 40)) AS r(brand, y, w)
JOIN control.T_Control_Autoreport_Brands b ON b.filter_value = r.brand;
GO
