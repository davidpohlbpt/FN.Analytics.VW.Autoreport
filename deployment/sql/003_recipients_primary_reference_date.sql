-- Aligns the existing control.T_Control_Autoreport_Recipients and _Runs tables with the
-- code (pptcreator/models/models.py). The recipients table is empty today; the guards make
-- the script safe to re-run and stop before dropping anything that still holds data.
--
-- Run against ReportDB. Nothing is dropped while a date column is still missing.

SET NOCOUNT ON;

-- ------------------------------- Recipients -------------------------------- #
IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'primary_date') IS NULL
    ALTER TABLE control.T_Control_Autoreport_Recipients ADD primary_date NVARCHAR(30) NULL;
IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'reference_date') IS NULL
    ALTER TABLE control.T_Control_Autoreport_Recipients ADD reference_date NVARCHAR(30) NULL;

-- Legacy week columns cannot be mapped to an AnalyseZeitpunkt automatically. Fail loudly
-- while any row still lacks a date instead of inventing one.
IF EXISTS (SELECT 1 FROM control.T_Control_Autoreport_Recipients
           WHERE primary_date IS NULL OR reference_date IS NULL)
BEGIN
    THROW 50000, 'Recipient rows have no primary_date/reference_date. Fill both with AnalyseZeitpunkt values (YYYY-MM-DD) first; no column was dropped.', 1;
END

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
    UPDATE control.T_Control_Autoreport_Recipients SET send_now = 0 WHERE is_active = 0;
    ALTER TABLE control.T_Control_Autoreport_Recipients DROP COLUMN is_active;
END

IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'reference_week') IS NOT NULL
    ALTER TABLE control.T_Control_Autoreport_Recipients DROP COLUMN reference_week;
IF COL_LENGTH('control.T_Control_Autoreport_Recipients', 'reference_year') IS NOT NULL
    ALTER TABLE control.T_Control_Autoreport_Recipients DROP COLUMN reference_year;

-- The unique constraint on the week columns would block one deck per row with identical dates
IF EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = 'UQ_Autoreport_Recipients'
           AND parent_object_id = OBJECT_ID('control.T_Control_Autoreport_Recipients'))
    ALTER TABLE control.T_Control_Autoreport_Recipients DROP CONSTRAINT UQ_Autoreport_Recipients;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Autoreport_Recipients_SendNow'
               AND object_id = OBJECT_ID('control.T_Control_Autoreport_Recipients'))
    CREATE INDEX IX_Autoreport_Recipients_SendNow
        ON control.T_Control_Autoreport_Recipients (template_id) WHERE send_now = 1;

-- ---------------------------------- Runs ----------------------------------- #
IF COL_LENGTH('control.T_Control_Autoreport_Runs', 'user_email') IS NULL
    ALTER TABLE control.T_Control_Autoreport_Runs ADD user_email NVARCHAR(1000) NULL;
IF COL_LENGTH('control.T_Control_Autoreport_Runs', 'recipient_id') IS NULL
    ALTER TABLE control.T_Control_Autoreport_Runs ADD recipient_id INT NULL;
IF COL_LENGTH('control.T_Control_Autoreport_Runs', 'primary_date') IS NULL
    ALTER TABLE control.T_Control_Autoreport_Runs ADD primary_date NVARCHAR(30) NULL;
IF COL_LENGTH('control.T_Control_Autoreport_Runs', 'reference_date') IS NULL
    ALTER TABLE control.T_Control_Autoreport_Runs ADD reference_date NVARCHAR(30) NULL;

-- Keep the old period strings visible in the new columns
UPDATE control.T_Control_Autoreport_Runs SET primary_date = current_period WHERE primary_date IS NULL;
UPDATE control.T_Control_Autoreport_Runs SET reference_date = reference_period WHERE reference_date IS NULL;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Autoreport_Runs_OpenClaim'
               AND object_id = OBJECT_ID('control.T_Control_Autoreport_Runs'))
    CREATE INDEX IX_Autoreport_Runs_OpenClaim
        ON control.T_Control_Autoreport_Runs (recipient_id) WHERE status = 'processing';

PRINT 'autoreport control tables aligned with the code.';
