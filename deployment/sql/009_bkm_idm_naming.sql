-- Email subject and PowerPoint file name start with "BKM IDM". Safe to run again.

UPDATE control.T_Control_Autoreport_Templates
SET target_file_name = N'BKM_IDM_Control_Center_{brand}_{current}_vs_{reference}',
    email_subject = N'BKM IDM Autoreport: Control Center {brand}: {current} vs. {reference}'
WHERE target_file_name = N'IDM_Control_Center_{brand}_{current}_vs_{reference}'
   OR email_subject = N'IDM Control Center {brand}: {current} vs. {reference}';
GO
