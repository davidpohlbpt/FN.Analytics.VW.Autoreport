# FN.Analytics.VW.Autoreport

Automated PowerPoint KPI reporting for VW, running as an AWS Lambda. For every brand
and reference period requested in the recipient list, a deck with six KPIs (current
week vs. reference week, overall and per commodity) is rendered from the VW template,
stored in S3 and e-mailed via SES.

Built on the internal `pycore` framework (resource mode `LOCAL`: SQL Server via pyodbc,
file storage under `/tmp`, secrets from environment variables). `pycore` is unchanged.

## Architecture

Three Lambdas orchestrated by a Step Functions state machine
(`deployment/state_machine.asl.json`), all built from the same container image with
different handlers:

```
EventBridge (weekly) ──┐
EventBridge (5 min)  ──┴──> Step Functions
                              Plan   (Lambda 1, plan_handler)   recipient table -> [ReportRequest]
                              Map over requests (concurrency 2)
                                Render (Lambda 2, render_handler) ReportRequest -> deck in S3
                                Send   (Lambda 3, send_handler)   deck in S3 -> SES e-mail
```

| Lambda | Handler | Input | Output | Side effects |
|---|---|---|---|---|
| 1 Plan | `pptcreator.lambda_handler.plan_handler` | `{"trigger": "scheduled"\|"adhoc", "template_id": 1}` | `{"run_id", "count", "requests": [...]}` | run log rows `queued`; `send_now` cleared for ad hoc rows |
| 2 Render | `pptcreator.lambda_handler.render_handler` | one `ReportRequest` (`deployment/events/render_request.json`) | `RenderResult` (`bucket`, `s3_key`, `file_name`, `slides`, `email_subject`) | deck in S3; run log `rendered`/`failed`; raises on failure |
| 3 Send | `pptcreator.lambda_handler.send_handler` | the `RenderResult` (+ optional `recipients` override) | `{"status": "sent", "message_id"}` | SES mail; run log `sent`/`failed` |
| all-in-one | `pptcreator.lambda_handler.handler` | `{"mode": "manual"\|"scheduled"\|"adhoc", ...}` | summary per deck | same, in one process (local runs, single-Lambda deployment) |

Lambda 2 is the core:

```
render_deck(request)
  - get_template_config        (T_Control_Autoreport_Templates + _Mappings -> TemplateConfig, KpiDefinitions)
  - s3_sync.download_template  (template_link s3://... -> pycore storage in /tmp)
  - get_kpi_deck_config
      - discover_chart_slots   (template: 2 overview charts, N commodity slots)
      - RoutingKpiSource.fetch (per KPI: frontend = DQN chart API, backend = SQL, stub)
      - build_output_slides    (KPIs x [overview + paginated detail slides])
      - get_template_config    (.pptx shapes: positions, fonts, legend)
  - graph_create_ppt           (python-pptx rendering -> pycore storage)
  - s3_sync.upload_output      (-> target_location of the template, or the default bucket)
```

The legacy per-template pipeline (`graph_steer_creation_process`, `T_CONTROL_PptCreator_*`,
Config Center) is still present and used by the older tests.

## Control tables (ReportDB, schema `control`)

DDL in `deployment/sql/001_autoreport_tables.sql`, example seed in `002_seed_vw_weekly.sql`.

| Table | Purpose | Key columns |
|---|---|---|
| `T_Control_Autoreport_Templates` | what a report is | `template_link` (`s3://bucket/key`), `language`, `target_file_name` (pattern with `{brand} {current} {reference}`), `target_location`, `email_subject` |
| `T_Control_Autoreport_Mappings` | one row per KPI of a template | `kpi_key`, `kpi_order`, `slide_title`, `slide_subtitle`, `source` (`frontend`/`backend`/`stub`), DQN ids (`menu_item_id`, `report_id`, `tile_id`, `chart_id`) or `query_key`, `palette_json`, `average_label` |
| `T_Control_Autoreport_Brands` | brand master list (frontend dropdown) | `brand_name` (display), `filter_value` (`EK_ORG` value), `is_active` |
| `T_Control_Autoreport_Recipients` | one row per deck a user wants | `template_id`, `email`, `brand_id` (FK Brands), `reference_year` + `reference_week` (ISO, **mandatory**, no default), `send_now`, `is_active`; unique per (email, template, brand, reference week). Same brand with several weeks = several decks; rows with identical (template, brand, week) share one deck |
| `T_Control_Autoreport_Runs` | audit log | `run_id`, `brand`, periods, `status` (`queued`/`rendered`/`sent`/`failed`), `s3_key`, `message_id`, `error` |

Data sources per KPI:

- `leitstand` (used for all six Control Center KPIs): `pptcreator/kpi/leitstand_source.py`.
  Slice columns, labels (Translation DB, keyed by column name), colours
  (`T_Chart_GeometryOption.background.color`) and legend order (`legend.sorting`) are read
  from the Control Center chart config for the mapping's `chart_id`; the numbers come from
  `ReportDB.dbo.T_RESULT_Leitstand_Overview` with `MOD = 'Alle' AND EK_ORG = <brand>`
  (grouped by `COM` for the commodity slides). A week is resolved to the latest
  `AnalyseZeitpunkt` in that ISO week, else the latest before it. "Ø" for KPI 1 is the
  BKA-weighted `UpdatedAvgAge` (days). Read-only.

  | KPI | chart_id | columns |
  |---|---|---|
  | BKA nach Aktualisierung | 12000 | UpdatedPastYear, UpdatedPast1to2Years, UpdatedPast2To4Years, UpdatedPast4To6Years, UpdatedOver6Years, NoUpdateData |
  | BKA nach Bearbeitungsstatus | 12002 | BearbSynchron, BearbÜberarbeitungBes, BearbÜberarbeitungLief, BearbÜberarbeitungPCP |
  | UVB Fehler nach Fehlercode | 12004 | U0, U1, U2, U3 |
  | Rote BKAs | 12006 | Red0to10, Red11to52, RedOver52 |
  | BKA nach Abgleichstatus | 120013 | Gruen, Gelb, Rot, Grau |
  | Saisonalität von Kapazitäten | 120017 | Kap1, Kap2to5, Kap6to10, KapOver10, KapNoData |
- `frontend`: DQN chart API (`pptcreator/kpi/frontend_source.py`). Needs the mask filter
  field names for brand / commodity / period (`DQN_FILTER_BRAND`, `DQN_FILTER_COMMODITY`,
  `DQN_FILTER_PERIOD`). Colours come from the chart unless `palette_json` is set.
- `backend`: SQL on the KPI table (`pptcreator/kpi/sql_source.py`). `query_key` selects a
  query from `QUERIES`; the `default` query targets `KPI_TABLE` (env) in long format
  `commodity, category, value, avg_text`. Replace once the real table is known.
- `stub`: deterministic dummy data for testing.

## Configuration

All settings are environment variables (see `.env.example`, `pptcreator/config.py`).
Key switches:

| Variable | Purpose |
|---|---|
| `RESOURCE_TYPE`, `APP_NAME`, `LOCAL_BLOB_DIR`, `LOCAL_SQLSERVER_CONN_STR` | pycore resources (ReportDB) |
| `SQL_CONN_SSM_PARAM` (+ `SQL_ODBC_DRIVER`, `SQL_ENCRYPT`, `SQL_TRUST_SERVER_CERTIFICATE`) | Lambda: read an ADO-style connection string (`Server=..;Initial Catalog=..;User ID=..;Password=..`) from SSM and set `LOCAL_SQLSERVER_CONN_STR`/`LOCAL_SQLSERVER_DB` |
| `S3_OUTPUT_BUCKET` | upload decks to `s3://<S3_OUTPUT_BUCKET>/<S3_OUTPUT_PREFIX>/`, overriding `target_location` of the template row |
| `AUTOREPORT_SCHEMA`, `DEFAULT_TEMPLATE_ID` | control tables |
| `S3_ENABLED`, `S3_BUCKET`, `S3_TEMPLATE_KEY`, `S3_OUTPUT_PREFIX` | defaults when the template row has no S3 links |
| `MAIL_ENABLED`, `SES_SENDER`, `SES_RECIPIENTS_MODE` | e-mail |
| `KPI_SOURCE_OVERRIDE` (`stub`/`frontend`/`backend`) | force one source for all KPIs (testing) |
| `KPI_TABLE`, `DQN_FILTER_*` | backend / frontend source specifics |
| `AWS_REGION_NAME` | boto3 region (`AWS_REGION` is reserved in Lambda) |

## Local development

```powershell
poetry install --with test
Copy-Item .env.example .env   # fill in values
poetry run pytest
poetry run pptcreator manual --brand Audi --reference KW37 --recipient you@example.com
```

### Preview a deck from ReportDB (no AWS, no control tables)

With the VPN tunnel up and `LOCAL_SQLSERVER_CONN_STR` in `.env`:

```powershell
poetry run python -m pptcreator.preview --brand "VW PKW" --current 2025-11-18 --reference previous --png
```

Reads the six Control Center KPIs live (read-only), renders with the VW template and
writes `previews/<name>.pptx` (gitignored); `--png` also exports every slide as PNG via
PowerPoint (needs `pywin32`, dev only). `--current latest` uses the newest snapshot,
`--reference previous` the snapshot before the current one; dates and weeks
(`2025-KW46`) work as well.

### Run the real pipeline locally, driven by the control tables

`pptcreator.preview_control` uses the same code path as the Lambdas: template, mappings,
brands and recipients come from `control.T_Control_Autoreport_*`, one deck per
recipient/brand.

```powershell
# every active recipient/brand, reference week from the recipient row
poetry run python -m pptcreator.preview_control

# one brand, or override the reference week for a quick test
poetry run python -m pptcreator.preview_control --brand Audi --current 2025-KW48 --reference 2025-KW40
```

Requirements: `RESOURCE_TYPE=LOCAL` (default in `.env`), the control tables filled, and
the template in `<LOCAL_BLOB_DIR>/<storage_container>/` (e.g.
`C:\temp\autoreport_data\ppt_creator\VW_Template_Overview.pptx`) because `S3_ENABLED=false`.
Decks land in `previews/`; the run log is written to `T_Control_Autoreport_Runs`.
`--reference db` (the default) uses the recipient row's week and falls back to the
snapshot before the current one if that week has no data for the brand.

The equivalent through the Lambda entry points:

```powershell
poetry run pptcreator scheduled --current 2025-KW48
poetry run pptcreator manual --brand Audi --reference 2025-KW40 --current 2025-KW48
```


```powershell
poetry run python -m pptcreator.preview --brand "VW PKW" --current 2025-11-18 --reference previous --png
```

Reads the six Control Center KPIs live (read-only), renders with the VW template and
writes `previews/<name>.pptx` (gitignored); `--png` also exports every slide as PNG via
PowerPoint (needs `pywin32`, dev only). `--current latest` uses the newest snapshot,
`--reference previous` the snapshot before the current one; dates and weeks
(`2025-KW46`) work as well.

With `S3_ENABLED=false` the template must exist in `<LOCAL_BLOB_DIR>/<storage_container>/`;
with `MAIL_ENABLED=false` the deck is rendered but not sent. Rendered decks from the
tests are written to `tests/result/` for visual inspection.

## Deployment

- `deployment/Dockerfile` -- Lambda container image. Installs ODBC Driver 18, then
  `requirements-docker.txt` (pinned, generated from `poetry.lock`) with `pycore` from
  the vendored wheel in `vendor/`. No credentials are needed at build time.
- `deployment/certs/` -- drop internal root CA `.pem` files here if the DQN host or
  SQL Server use a VW-internal CA; they are bundled into the image and trusted
  automatically (never committed).
- `deployment/template.yaml` -- SAM stack: Lambda in VPC, S3 bucket, EventBridge weekly
  rule (disabled by default), IAM, log group. Secrets are resolved from Secrets Manager.
- `.github/workflows/deploy.yml` -- PRs and pushes to `main` run tests only. Tags `v*`
  and manual runs also build, push to ECR, `sam deploy`, and upload the template to
  the bucket (branches -> dev, tags `v*` -> prod).

After changing dependencies: `poetry lock`, then `python deployment/export_requirements.py`.
After a pycore update: see `vendor/README.md`.

Local image build and smoke test (Lambda Runtime Interface Emulator is part of the base image):

```powershell
docker build -f deployment/Dockerfile -t vw-autoreport .
docker run -d --name autoreport -p 9000:8080 `
  -v "${PWD}\tests\unit\test_data\VW_Template_Overview.pptx:/opt/template/VW_Template_Overview.pptx:ro" `
  -e S3_ENABLED=false -e MAIL_ENABLED=false `
  -e LOCAL_SQLSERVER_CONN_STR="Driver={ODBC Driver 18 for SQL Server};Server=x;Database=ReportDB;Uid=u;Pwd=p;" `
  -e BASE_REQUEST_URL=dqn.example -e ENDPOINTBASEPATH=https://dqn.example vw-autoreport
docker exec autoreport sh -c "mkdir -p /tmp/autoreport_data/ppt_creator && cp /opt/template/*.pptx /tmp/autoreport_data/ppt_creator/"
Invoke-WebRequest -Method Post -Uri "http://localhost:9000/2015-03-31/functions/function/invocations" `
  -ContentType application/json -Body '{"mode":"manual","brand":"Audi","current_period":"KW45","reference_period":"KW37"}'
docker rm -f autoreport
```

Manual push to ECR without the workflow:

```powershell
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker tag vw-autoreport:latest <account>.dkr.ecr.<region>.amazonaws.com/vw-autoreport:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/vw-autoreport:latest
```

## Template contract

- Only `doughnut` charts are supported (`pptcreator/models/enum.py`).
- Chart rows are `{"category": ..., "value": ...}` dicts (first key category, second value).
- Shapes are matched by name suffix: `"<object> Chart"`, `"<object> Headline"`,
  `"<object> Box"`, `"<object> Total"`; a shape named exactly `Legend` is the slide legend.
- Template slide 1 must hold exactly two charts (reference, current); template slide 2
  holds the commodity slots and is repeated when a brand has more commodities than slots.
- Other non-empty text boxes (e.g. `Targets` and the data source line) are copied as is,
  with `{brand}`, `{week}` (current week), `{laufkennung}` (fixed `V11` for now) and
  `{target_label1|2}` / `{target_text1|2}` (empty for now) filled in. Unknown
  placeholders stay visible. Empty boxes such as `Chart 2 Status` are not rendered.
