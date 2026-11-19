-- Control tables for the VW Autoreport (ReportDB). SQL Server syntax.
-- Mirrors pptcreator/models/models.py (AutoreportTemplates / Mappings / Brands / Recipients / Runs).
-- The legacy T_CONTROL_PptCreator_* tables are not touched.

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
    source         NVARCHAR(20)   NOT NULL CONSTRAINT CK_Autoreport_Mappings_Source CHECK (source IN ('leitstand','frontend','backend','stub')),
    menu_item_id   INT            NULL,   -- frontend: DQN menu item
    report_id      INT            NULL,   -- frontend: DQN report
    tile_id        INT            NULL,   -- frontend: DQN tile
    chart_id       INT            NULL,   -- frontend/leitstand: DQN chart (Control Center donuts: 12000, 12002, 12004, 12006, 120013, 120017)
    query_key      NVARCHAR(100)  NULL,   -- backend: key in pptcreator/kpi/sql_source.py QUERIES
    palette_json   NVARCHAR(2000) NULL,   -- {"category": "rgb(r, g, b)", ...} in display order
    average_label  NVARCHAR(20)   NULL CONSTRAINT DF_Autoreport_Mappings_Avg DEFAULT N'Ø',
    is_active      BIT            NOT NULL CONSTRAINT DF_Autoreport_Mappings_Active DEFAULT 1,
    CONSTRAINT UQ_Autoreport_Mappings UNIQUE (template_id, kpi_key)
);
GO

IF OBJECT_ID('control.T_Control_Autoreport_Brands', 'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_Brands (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    brand_name   NVARCHAR(200) NOT NULL,   -- shown in the frontend dropdown
    filter_value NVARCHAR(200) NOT NULL,   -- exact EK_ORG value in dbo.T_RESULT_Leitstand_Overview
    is_active    BIT           NOT NULL CONSTRAINT DF_Autoreport_Brands_Active DEFAULT 1,
    CONSTRAINT UQ_Autoreport_Brands_Filter UNIQUE (filter_value)
);
GO

-- One row per deck a user wants, maintained by the frontend. The two snapshot dates are
-- AnalyseZeitpunkt values (YYYY-MM-DD); send_now = 1 is the only trigger of a deck and is
-- cleared by the record Lambda once the mail left, or by the frontend.
IF OBJECT_ID('control.T_Control_Autoreport_Recipients', 'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_Recipients (
    id             INT IDENTITY(1,1) PRIMARY KEY,
    template_id    INT           NOT NULL REFERENCES control.T_Control_Autoreport_Templates(id),
    email          NVARCHAR(1000) NOT NULL,
    brand_id       INT           NOT NULL REFERENCES control.T_Control_Autoreport_Brands(id),
    primary_date   NVARCHAR(30)  NOT NULL,   -- current snapshot,    e.g. 2025-11-28
    reference_date NVARCHAR(30)  NOT NULL,   -- comparison snapshot, e.g. 2025-10-28
    send_now       BIT           NULL CONSTRAINT DF_Autoreport_Recipients_SendNow DEFAULT 0,
    last_edited_at DATETIME2     NULL
);
GO
CREATE INDEX IX_Autoreport_Recipients_SendNow
    ON control.T_Control_Autoreport_Recipients (send_now, template_id) WHERE send_now = 1;
GO

IF OBJECT_ID('control.T_Control_Autoreport_Runs', 'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_Runs (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    run_id           NVARCHAR(100)  NOT NULL,   -- one UUID per plan invocation
    template_id      INT            NOT NULL,
    user_email       NVARCHAR(1000) NULL,       -- email of the recipient row
    recipient_id     INT            NULL,       -- T_Control_Autoreport_Recipients.id; open claim while 'processing'
    brand            NVARCHAR(200)  NOT NULL,
    primary_date     NVARCHAR(30)   NULL,       -- current snapshot of the deck
    reference_date   NVARCHAR(30)   NULL,       -- comparison snapshot of the deck
    current_period   NVARCHAR(50)   NULL,       -- legacy column, older rows only
    reference_period NVARCHAR(50)   NULL,       -- legacy column, older rows only
    [trigger]        NVARCHAR(20)   NOT NULL,
    status           NVARCHAR(20)   NOT NULL,   -- processing | rendered | sent | skipped | failed
    s3_key           NVARCHAR(1000) NULL,
    message_id       NVARCHAR(200)  NULL,
    error            NVARCHAR(4000) NULL,
    created_at       DATETIME2      NULL,
    updated_at       DATETIME2      NULL
);
CREATE INDEX IX_Autoreport_Runs_RunId ON control.T_Control_Autoreport_Runs (run_id);
CREATE INDEX IX_Autoreport_Runs_OpenClaim ON control.T_Control_Autoreport_Runs (recipient_id)
    WHERE status = 'processing';
GO
