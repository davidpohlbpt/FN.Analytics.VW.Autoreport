-- Aligns the existing control.T_Control_Autoreport_Recipients and _Runs tables with the
-- code (pptcreator/models/models.py). The recipients table is empty today; the guards make
-- the script safe to re-run and stop before dropping anything that still holds data.
--
-- Run against ReportDB. Nothing is dropped while a date column is still missing.

SET NOCOUNT ON;

-- ------------------------------- Recipients -------------------------------- #
-- Superseded by 006_dropdown_runs.sql: the frontend owns this table with report_week /
-- comparison_week. Only stages that still have the legacy week columns of 001 (and no
-- report_week) run this section; column references go through EXEC so the batch also
-- compiles where the columns do not exist.
IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'report_week') IS NOT NULL
    PRINT 'Recipients already use report_week / comparison_week (frontend); section skipped.';
ELSE
BEGIN
    IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'primary_date') IS NULL
        ALTER TABLE control.T_Control_Autoreport_Recipients ADD primary_date NVARCHAR(30) NULL;
    IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'reference_date') IS NULL
        ALTER TABLE control.T_Control_Autoreport_Recipients ADD reference_date NVARCHAR(30) NULL;

    -- Legacy week columns cannot be mapped to an AnalyseZeitpunkt automatically. Fail loudly
    -- while any row still lacks a date instead of inventing one.
    DECLARE @missing INT;
    EXEC sp_executesql
        N'SELECT @n = COUNT(*) FROM control.T_Control_Autoreport_Recipients WHERE primary_date IS NULL OR reference_date IS NULL',
        N'@n INT OUTPUT', @n = @missing OUTPUT;
    IF @missing > 0
        THROW 50000, 'Recipient rows have no primary_date/reference_date. Fill both with AnalyseZeitpunkt values (YYYY-MM-DD) first; no column was dropped.', 1;

    IF EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('control.T_Control_Autoreport_Recipients')
                 AND name = 'primary_date' AND is_nullable = 1)
        ALTER TABLE control.T_Control_Autoreport_Recipients ALTER COLUMN primary_date NVARCHAR(30) NOT NULL;
    IF EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('control.T_Control_Autoreport_Recipients')
                 AND name = 'reference_date' AND is_nullable = 1)
        ALTER TABLE control.T_Control_Autoreport_Recipients ALTER COLUMN reference_date NVARCHAR(30) NOT NULL;

    -- is_active is replaced by send_now: inactive rows must never be picked up by the poller
    IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'is_active') IS NOT NULL
    BEGIN
        EXEC (N'UPDATE control.T_Control_Autoreport_Recipients SET send_now = 0 WHERE is_active = 0');
        ALTER TABLE control.T_Control_Autoreport_Recipients DROP COLUMN is_active;
    END

    IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'reference_week') IS NOT NULL
        ALTER TABLE control.T_Control_Autoreport_Recipients DROP COLUMN reference_week;
    IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'reference_year') IS NOT NULL
        ALTER TABLE control.T_Control_Autoreport_Recipients DROP COLUMN reference_year;
END

-- The unique constraint on the week columns would block one deck per row with identical dates
IF EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = 'UQ_Autoreport_Recipients'
           AND parent_object_id = OBJECT_ID('control.T_Control_Autoreport_Recipients'))
    ALTER TABLE control.T_Control_Autoreport_Recipients DROP CONSTRAINT UQ_Autoreport_Recipients;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Autoreport_Recipients_SendNow'
               AND object_id = OBJECT_ID('control.T_Control_Autoreport_Recipients'))
    CREATE INDEX IX_Autoreport_Recipients_SendNow
        ON control.T_Control_Autoreport_Recipients (template_id) WHERE send_now = 1;

-- ---------------------------------- Runs ----------------------------------- #
IF COL_LENGTH('control.T_Control_Autoreport_Runs', 'recipient_id') IS NULL
    ALTER TABLE control.T_Control_Autoreport_Runs ADD recipient_id INT NULL;
-- Existing run snapshots are consolidated by 007_simplify_autoreport_runs.sql.

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Autoreport_Runs_OpenClaim'
               AND object_id = OBJECT_ID('control.T_Control_Autoreport_Runs'))
    CREATE INDEX IX_Autoreport_Runs_OpenClaim
        ON control.T_Control_Autoreport_Runs (recipient_id) WHERE status = 'processing';

PRINT 'autoreport control tables aligned with the code.';
