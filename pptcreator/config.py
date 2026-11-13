"""Project settings.

All values are read from environment variables (case-insensitive) and can be set in
``.env`` for local runs. In AWS Lambda they are provided by the SAM template; secrets
are injected from Secrets Manager into the environment and read by pycore's EnvVault.
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class CreatorSettings(BaseSettings):

    # ------------------------------- Database -------------------------------- #
    app_db_schema: str = "control"
    """Schema of the control tables (legacy templates/mappings/recipients)."""

    autoreport_schema: str = "control"
    """Schema of the T_Control_Autoreport_* tables in ReportDB."""

    default_template_id: int | None = None
    """Template used when an event does not name one; None -> the only active template."""

    plan_template_ids: str | None = None
    """Templates planned per run by the plan Lambda: comma-separated ids (``1,3``) or
    ``all``. Empty -> ``default_template_id``, else all active templates. A
    ``template_id`` / ``template_ids`` in the event takes precedence."""

    # ------------------------------- Storage --------------------------------- #
    storage_container: str = "ppt_creator"
    """Container (folder) in pycore storage holding the template and the outputs."""

    template_file_name: str = "VW_Template_Overview.pptx"
    """Template file name inside ``storage_container``."""

    # --------------------------------- S3 ------------------------------------ #
    s3_enabled: bool = False
    """When false, no S3 call is made; template and outputs stay in pycore storage."""

    s3_bucket: str | None = None
    s3_template_key: str = "templates/VW_Template_Overview.pptx"
    s3_output_prefix: str = "reports"

    s3_output_bucket: str | None = None
    """When set, decks are uploaded to s3://<s3_output_bucket>/<s3_output_prefix>/,
    overriding ``target_location`` of the template row."""

    # --------------------------------- SES ----------------------------------- #
    mail_enabled: bool = False
    """When false, the e-mail step is skipped and only logged."""

    ses_sender: str | None = None
    """Verified SES sender address."""

    ses_recipients_mode: str = Field(default="bcc", pattern="^(bcc|to)$")
    """Whether recipients are placed in ``To`` or ``Bcc``."""

    ses_max_attachment_mb: int = 35
    """SES hard limit is 40 MB for the whole raw message; keep a safety margin."""

    aws_region: str | None = Field(default=None, validation_alias="AWS_REGION_NAME")
    """Region for boto3 clients. Read from ``AWS_REGION_NAME`` because ``AWS_REGION`` is a
    reserved Lambda variable. ``None`` lets boto3 use its default resolution (which in
    Lambda is ``AWS_REGION`` anyway)."""

    # ------------------------------- Report ---------------------------------- #
    report_language: str = Field(default="DE", pattern="^(DE|EN)$")
    commodity_charts_per_slide: int = 7
    """Number of commodity doughnuts on the detail template slide (Chart 3..9)."""

    kpi_source_override: str | None = Field(default=None, pattern="^(stub|frontend|backend|leitstand)$")
    """Force one data source for all KPIs regardless of the mapping table (testing)."""


settings = CreatorSettings()
