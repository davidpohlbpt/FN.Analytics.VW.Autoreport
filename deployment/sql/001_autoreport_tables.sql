-- Control tables for the VW Autoreport (ReportDB). SQL Server syntax.
-- Mirrors pptcreator/models/models.py (AutoreportTemplates / Mappings / Recipients / Runs).

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'control')
    EXEC('CREATE SCHEMA control');
GO

IF OBJECT_ID('control.T_Control_Autoreport_Templates', 'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_Templates (
    id                           INT IDENTITY(1,1) PRIMARY KEY,
    name                         NVARCHAR(200)  NOT NULL,
    template_link                NVARCHAR(1000) NOT NULL,   -- s3://bucket/key  or  container/file.pptx
    language                     NVARCHAR(2)    NOT NULL CONSTRAINT CK_Autoreport_Templates_Lang CHECK (language IN ('DE','EN')),
    target_file_name             NVARCHAR(500)  NOT NULL,   -- pattern with {brand} {current} {reference}
    target_location              NVARCHAR(1000) NULL,       -- s3://bucket/prefix ; NULL -> Lambda default bucket/prefix
    default_reference_weeks_back INT            NULL CONSTRAINT DF_Autoreport_Templates_RefWeeks DEFAULT 8,
    commodity_charts_per_slide   INT            NULL,       -- NULL -> all chart slots on template slide 2
    email_subject                NVARCHAR(500)  NULL,       -- pattern with {brand} {current} {reference}
    is_active                    BIT            NOT NULL CONSTRAINT DF_Autoreport_Templates_Active DEFAULT 1
);
GO

IF OBJECT_ID('control.T_Control_Autoreport_Mappings', 'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_Mappings (
    id             INT IDENTITY(1,1) PRIMARY KEY,
    template_id    INT            NOT NULL REFERENCES control.T_Control_Autoreport_Templates(id),
    kpi_key        NVARCHAR(100)  NOT NULL,
    kpi_order      INT            NOT NULL CONSTRAINT DF_Autoreport_Mappings_Order DEFAULT 0,
    kpi_name       NVARCHAR(200)  NOT NULL,
    slide_title    NVARCHAR(500)  NOT NULL,
    slide_subtitle NVARCHAR(1000) NULL,
    source         NVARCHAR(20)   NOT NULL CONSTRAINT CK_Autoreport_Mappings_Source CHECK (source IN ('frontend','backend','stub')),
    menu_item_id   INT            NULL,   -- frontend: DQN menu item
    report_id      INT            NULL,   -- frontend: DQN report
    tile_id        INT            NULL,   -- frontend: DQN tile
    chart_id       INT            NULL,   -- frontend: DQN chart
    query_key      NVARCHAR(100)  NULL,   -- backend: key in pptcreator/kpi/sql_source.py QUERIES
    palette_json   NVARCHAR(2000) NULL,   -- {"category": "rgb(r, g, b)", ...} in display order
    average_label  NVARCHAR(20)   NULL CONSTRAINT DF_Autoreport_Mappings_Avg DEFAULT N'Ø',
    is_active      BIT            NOT NULL CONSTRAINT DF_Autoreport_Mappings_Active DEFAULT 1,
    CONSTRAINT UQ_Autoreport_Mappings UNIQUE (template_id, kpi_key)
);
GO

IF OBJECT_ID('control.T_Control_Autoreport_Recipients', 'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_Recipients (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    template_id         INT           NOT NULL REFERENCES control.T_Control_Autoreport_Templates(id),
    email               NVARCHAR(500) NOT NULL,
    brand               NVARCHAR(200) NOT NULL,
    reference_timestamp NVARCHAR(50)  NULL,      -- 'KW37' or '2026-KW37'; NULL -> template default
    send_now            BIT           NULL CONSTRAINT DF_Autoreport_Recipients_SendNow DEFAULT 0,
    is_active           BIT           NULL CONSTRAINT DF_Autoreport_Recipients_Active DEFAULT 1,
    last_edited_at      DATETIME2     NULL
);
GO

IF OBJECT_ID('control.T_Control_Autoreport_Runs', 'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_Runs (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    run_id           NVARCHAR(100)  NOT NULL,
    template_id      INT            NOT NULL,
    brand            NVARCHAR(200)  NOT NULL,
    current_period   NVARCHAR(50)   NOT NULL,
    reference_period NVARCHAR(50)   NOT NULL,
    recipients       NVARCHAR(4000) NOT NULL,
    trigger          NVARCHAR(20)   NOT NULL,
    status           NVARCHAR(20)   NOT NULL,   -- queued | rendered | sent | failed
    s3_key           NVARCHAR(1000) NULL,
    message_id       NVARCHAR(200)  NULL,
    error            NVARCHAR(4000) NULL,
    created_at       DATETIME2      NULL,
    updated_at       DATETIME2      NULL
);
CREATE INDEX IX_Autoreport_Runs_RunId ON control.T_Control_Autoreport_Runs (run_id);
GO
