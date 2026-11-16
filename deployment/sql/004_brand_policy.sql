-- Per-brand deck presentation (ReportDB, schema control). SQL Server syntax.
-- Additive only: the frontend-owned tables (Templates / Mappings / Brands / Recipients)
-- are not altered. See pptcreator/kpi/commodity_policy.py and pptcreator/kpi/brand_policy.py.

IF OBJECT_ID('control.T_Control_Autoreport_BrandCommodities', 'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_BrandCommodities (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    brand_id     INT          NOT NULL REFERENCES control.T_Control_Autoreport_Brands(id),
    com_source   NVARCHAR(50) NOT NULL,   -- value in T_RESULT_Leitstand_Overview.COM
    com_label    NVARCHAR(50) NOT NULL,   -- label shown in the chart headline
    sort_order   INT          NOT NULL CONSTRAINT DF_Autoreport_BrandCommodities_Order DEFAULT 0,
    show_if_zero BIT          NOT NULL CONSTRAINT DF_Autoreport_BrandCommodities_Zero DEFAULT 1,
    is_active    BIT          NOT NULL CONSTRAINT DF_Autoreport_BrandCommodities_Active DEFAULT 1,
    CONSTRAINT UQ_Autoreport_BrandCommodities UNIQUE (brand_id, com_source)
);
GO

-- A brand with NO active rows here keeps the default behaviour: all commodities the KPI
-- source returns, source labels, source order, zero-valued commodities skipped.
-- Rows turn the brand into an explicit whitelist (rename + order + zero-fill).
IF OBJECT_ID('control.T_Control_Autoreport_BrandFeatures', 'U') IS NULL
CREATE TABLE control.T_Control_Autoreport_BrandFeatures (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    brand_id      INT           NOT NULL REFERENCES control.T_Control_Autoreport_Brands(id),
    feature_key   NVARCHAR(50)  NOT NULL,   -- e.g. 'footnote_text'
    feature_value NVARCHAR(200) NOT NULL,   -- '' switches the feature explicitly off
    is_active     BIT           NOT NULL CONSTRAINT DF_Autoreport_BrandFeatures_Active DEFAULT 1,
    CONSTRAINT UQ_Autoreport_BrandFeatures UNIQUE (brand_id, feature_key)
);
GO

-- A brand with NO active rows here gets the feature's default, which is "off".
-- Supported keys: 'footnote_text' (text of the template's {footnote} token).
-- Unknown keys are ignored with a warning, so a new brand quirk needs no schema change.

-- ------------------------------- Seed: VW PKW -------------------------------- #
-- VW PKW always shows these seven COMs on one detail slide, under these labels,
-- even when a COM has no data. Resolved by filter_value, never by a literal id.
IF NOT EXISTS (
    SELECT 1 FROM control.T_Control_Autoreport_BrandCommodities bc
    JOIN control.T_Control_Autoreport_Brands b ON b.id = bc.brand_id
    WHERE b.filter_value = N'VW PKW'
)
INSERT INTO control.T_Control_Autoreport_BrandCommodities
    (brand_id, com_source, com_label, sort_order, show_if_zero, is_active)
SELECT b.id, v.com_source, v.com_label, v.sort_order, 1, 1
FROM control.T_Control_Autoreport_Brands b
CROSS JOIN (VALUES
    (N'BC', N'BC', 10),
    (N'BI', N'BI', 20),
    (N'BM', N'BM', 30),
    (N'BN', N'BN', 40),
    (N'BX', N'BX', 50),
    (N'BP', N'CB', 60),   -- renamed
    (N'BL', N'ZB', 70)    -- renamed
) AS v(com_source, com_label, sort_order)
WHERE b.filter_value = N'VW PKW';
GO

-- Footnote text for the template's {footnote} token. Keep it free of placeholders:
-- fill_placeholders() substitutes in a single pass, so {brand}/{week} inside this text
-- would stay literal on the slide.
IF NOT EXISTS (
    SELECT 1 FROM control.T_Control_Autoreport_BrandFeatures bf
    JOIN control.T_Control_Autoreport_Brands b ON b.id = bf.brand_id
    WHERE b.filter_value = N'VW PKW' AND bf.feature_key = N'footnote_text'
)
INSERT INTO control.T_Control_Autoreport_BrandFeatures
    (brand_id, feature_key, feature_value, is_active)
SELECT b.id, N'footnote_text', N'Darstellung auf die Commodities BC, BI, BM, BN, BX, CB und ZB begrenzt.', 1
FROM control.T_Control_Autoreport_Brands b
WHERE b.filter_value = N'VW PKW';
GO
