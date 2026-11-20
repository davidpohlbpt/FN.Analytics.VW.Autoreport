-- One-time migration of the existing runs table; all referenced columns must exist.
-- Pause polling and drain workflows before applying this and deploying detect/render.
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE control.T_Control_Autoreport_Runs
    SET recipients = CASE
            WHEN NULLIF(LTRIM(RTRIM(recipients)), N'') IS NULL THEN user_email
            ELSE recipients
        END,
        current_period = COALESCE(primary_date, current_period),
        reference_period = COALESCE(reference_date, reference_period);

    ALTER TABLE control.T_Control_Autoreport_Runs
        DROP COLUMN user_email, primary_date, reference_date, [trigger], message_id, s3_key;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
