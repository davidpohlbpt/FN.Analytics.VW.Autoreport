# FN.Analytics.VW.Autoreport

Automated PowerPoint KPI reporting for VW, running as an AWS Lambda. For every brand
and reference period requested in the recipient list, a deck with six KPIs (current
week vs. reference week, overall and per commodity) is rendered from the VW template,
stored in S3 and e-mailed through Microsoft Graph.

Built on the internal `pycore` framework (resource mode `LOCAL`: SQL Server via pyodbc,
file storage under `/tmp`, secrets from environment variables). `pycore` is unchanged.

## Architecture

An EventBridge schedule calls `vw-autoreport-detect` every few minutes. Detect reads the
recipient rows with `send_now = 1`, writes `processing` claims and, only if there are new
requests, starts the Step Function. Render runs from the container image (pycore, ODBC
driver, VPC access to SQL Server and DQN). Detect and send email are separate ZIP
functions in `functions/`. Lambdas, Step Function and schedule are created by hand in AWS.

```
EventBridge (every 5 min, input {})
  -> Detect (ZIP, functions/vw-autoreport-detect.py) send_now rows -> claims -> Step Function
       Map over $.requests (MaxConcurrency 1)
         Render (image, lambdas/render.py)             one request -> deck in S3
         SendEmail (ZIP, vw-autoreport-sendemail)      render output -> Graph mail -> DB update -> delete deck
```

| Lambda | Handler | Input | Output | Side effects |
|---|---|---|---|---|
| Detect | `lambda_handler` (ZIP, `functions/vw-autoreport-detect.py`) | `{}` | starts the Step Function with `{"has_requests", "count", "requests": [{"template_id", "brand", "current_period", "reference_period", "recipients", "recipient_ids", "run_id"}]}` | run log rows `processing`; identical requests already processing are skipped |
| Render | `pptcreator.lambdas.render.handler` | one Step Functions request, or a hand-written one (`deployment/events/render_request.json`); template and KPI mappings are read from the control tables | `{"recipient", "recipient_id", "run_id", "brand", "bucket", "s3_key", "file_name", "email_subject"}` | deck in S3; run log `rendered`/`failed`; raises on failure |
| SendEmail | `lambda_function.lambda_handler` (ZIP, `functions/vw-autoreport-sendemail`) | the render output | `{"statusCode": 200, "body"}` | Graph BCC mail; then `send_now = 0`, run log `sent`, generated report deleted. On send failure: run log `failed`, `send_now` and report kept, raises |
| all-in-one | `pptcreator.lambda_handler.handler` | `{"mode": "adhoc"\|"manual", ...}` | summary per deck | render only, for local runs; no e-mail |

The render output is exactly the event read by `vw-autoreport-sendemail`. The Step
Functions Map handles one recipient per item. `tests/unit/test_lambda_handler.py` checks
render with the detect request format; `tests/unit/detect/test_detect.py` checks detect.
`pptcreator.lambda_handler.render_handler` remains as an alias.

Render is the core:

```
render_deck(request)
  - get_template_config        (T_Control_Autoreport_Templates + _Mappings)
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

DDL in `deployment/sql/001_autoreport_tables.sql`, example seed in `002_seed_vw_weekly.sql`,
per-brand presentation in `004_brand_policy.sql`, value under each donut in `005_kpi_metrics.sql`,
week dropdowns and the frontend's recipient columns in `006_dropdown_runs.sql`, and data source
wording in `008_kpi_data_source_text.sql`. Run 008 before deploying the application version
that reads its column.

| Table | Purpose | Key columns |
|---|---|---|
| `T_Control_Autoreport_Templates` | what a report is | `template_link` (`s3://bucket/key`), `language`, `target_file_name` (pattern with `{brand} {current} {reference}`), `target_location`, `email_subject` |
| `T_Control_Autoreport_Mappings` | one row per KPI of a template | `kpi_key`, `kpi_order`, `slide_title`, `slide_subtitle`, `source` (`frontend`/`backend`/`stub`), DQN ids (`menu_item_id`, `report_id`, `tile_id`, `chart_id`) or `query_key`, `palette_json`, `average_label` (deprecated: only used when the KPI has no row in `T_Control_Autoreport_KpiMetrics`) |
| `T_Control_Autoreport_KpiMetrics` | value under each donut, per KPI (all brands/templates) | `kpi_key`, `metric_type` (`avg_age`/`percent`/`ratio`/`count`), `numerator_columns` / `denominator_columns` (comma-separated columns of `T_RESULT_Leitstand_Overview`, summed with the donut's filter; `NULL` = donut total), `numerator_not_null_column` (only rows where it is not NULL), `label` (prefix, e.g. `Ø`), `explanation_text` (`{kpi_explanation}` on overview and COM slides), `showed_bkas` (data source wording on both slides), `is_active`. Structured on purpose, no SQL; invalid rows are ignored with a warning. **No active row ⇒ previous behaviour** (`average_label`). Percent `45 %` (whole number), ratio `120 / 30`; no data ⇒ `0 %` / `0 / 0` |
| `T_Control_Autoreport_Brands` | brand master list (frontend dropdown) | `brand_name` (display), `filter_value` (`EK_ORG` value), `is_active` |
| `T_Control_Autoreport_BrandCommodities` | per-brand commodity presentation | `brand_id` (FK Brands), `com_source` (`COM` in `T_RESULT_Leitstand_Overview`), `com_label` (headline label, enables renames), `sort_order`, `show_if_zero`, `is_active`. **No active rows for a brand ⇒ default behaviour** (all COMs, source labels/order, zeros skipped). Rows ⇒ whitelist + rename + order + zero-fill |
| `T_Control_Autoreport_BrandFeatures` | per-brand feature switches | `brand_id` (FK Brands), `feature_key`, `feature_value` (`''` = explicitly off), `is_active`. **No active rows ⇒ feature off.** Supported key: `footnote_text` = text of the template's `{footnote}` token, so only that brand shows a footnote. Unknown keys are ignored with a warning |
| `T_Control_Autoreport_Recipients` | one row per deck a user wants; maintained by the frontend | `template_id`, `email`, `brand_id` (FK Brands), `report_week` + `comparison_week` (**mandatory**; the dropdown string `LAUFKENNUNG (LAUF_KW)`, e.g. `V01-B (46/2025)`; dates `2025-11-28` and `2025-KW46` are accepted too), `send_now`, `IsDeleted` (soft delete, never planned). The backend splits the run string and finds the snapshot by `LAUFKENNUNG` + `LAUF_KW` in `T_RESULT_Leitstand_Overview`. `send_now = 1` is the only trigger: the 5-minute poller picks those rows. One deck per row, even for identical brand and weeks; two rows with the same brand and weeks write the same file name (later overwrites earlier) |
| `dbo.V_Autoreport_DropdownValues` | frontend dropdowns (`006_dropdown_runs.sql`) | active brands; `report_week` = every run in `T_RESULT_Leitstand_Overview` as `LAUFKENNUNG (LAUF_KW)`, `comparison_week` = the same without the latest run, `sort_date` = the run's AnalyseZeitpunkt (the frontend sorts by it, newest first, through its data source config `T_CONTROL_Report_DataSourceColumns` (data source 9502, `OrderBy`/`OrderParameter`), also set by 006; a view cannot carry an order). Read live, so a new weekly load appears automatically; snapshots without `LAUFKENNUNG` are not offered. `T_Control_Autoreport_Weeks` is no longer used |
| `T_Control_Autoreport_Runs` | audit log and the claim that prevents double sends | `run_id`, `template_id`, `recipients` (one email snapshot per deck), `recipient_id`, `brand`, `current_period` (`report_week`), `reference_period` (`comparison_week`), `status` (`processing`/`rendered`/`sent`/`skipped`/`failed`), `error`, `created_at`, `updated_at` |

For existing databases, pause the detect poller and let running workflows finish before
applying `deployment/sql/007_simplify_autoreport_runs.sql` and deploying the updated
detect/render code; resume polling after both are updated. This is a one-time migration
for the existing schema, not needed for fresh tables created by `001`. It preserves
email and period snapshots, then drops the redundant runs-table columns `user_email`,
`primary_date`, `reference_date`, `trigger`, `message_id`, and `s3_key`. The S3 key
remains in the render/send workflow payload; recipient-table columns are unchanged.

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
poetry run pptcreator adhoc       # render every row with send_now = 1 locally, no e-mail
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

The brand policy (`T_Control_Autoreport_BrandCommodities` / `_BrandFeatures`) is applied
whenever the tables exist; without them every brand keeps the default behaviour.
`--no-brand-policy` skips it explicitly.

With `S3_ENABLED=false` the template must exist in `<LOCAL_BLOB_DIR>/<storage_container>/`.
Local runs render decks but never send e-mails. Rendered decks from the tests are written
to `tests/result/` for visual inspection.

## Deployment

- `deployment/Dockerfile` -- Lambda container image for render. Installs
  ODBC Driver 18, then `requirements-docker.txt` (pinned, generated from `poetry.lock`)
  with `pycore` from the vendored wheel in `vendor/`. No credentials are needed at build
  time. Detect and send email are not in the image.
- `functions/vw-autoreport-detect.py` -- ZIP Lambda that finds new `send_now` rows,
  writes `processing` claims and starts the Step Function. Needs `STATE_MACHINE_ARN`,
  `REPORT_PARAM`, the `pyodbc` layer, `states:StartExecution` and reserved concurrency 1.
- `functions/vw-autoreport-sendemail/` -- code of the Microsoft Graph send Lambda. See
  [Send email Lambda (ZIP)](#send-email-lambda-zip).
- `deployment/certs/` -- drop internal root CA `.pem` files here if the DQN host or
  SQL Server use a VW-internal CA; they are bundled into the image and trusted
  automatically (never committed).
- AWS resources (Lambdas, Step Function, EventBridge schedule, IAM) are created by hand.
  Image Lambda: render `pptcreator.lambdas.render.handler`.
  Schedule: `rate(5 minutes)` -> `vw-autoreport-detect`, input `{}`.
- `.github/workflows/deploy.yml` -- PRs and pushes to `main` run tests only. Tags `v*`
  and manual runs also build, push to ECR and point the Lambdas in `LAMBDA_FUNCTIONS`
  at the new image (branches -> dev, tags `v*` -> prod).

After changing dependencies: `poetry lock`, then `python deployment/export_requirements.py`.
After a pycore update: see `vendor/README.md`.

For render failure notifications, set `SNS_URL` on the render Lambda to the SNS
topic ARN and grant its execution role `sns:Publish` on that topic. Add and confirm
an email subscription to receive notifications. Catchable handler failures publish
an alert and still raise the original error to Step Functions; SNS failures are
logged without masking it. Once a request is parsed, failures also attempt to mark
its run `failed` with the error. Invalid inputs before parsing cannot reliably
identify a run row, but still trigger an alert. Database logging is best effort.
Hard Lambda timeouts, out-of-memory termination and import/initialization errors
are outside this handler; use AWS monitoring for those.

Local image build and smoke test (Lambda Runtime Interface Emulator is part of the base image):

```powershell
docker build -f deployment/Dockerfile -t vw-autoreport .
docker run -d --name autoreport -p 9000:8080 `
  -v "${PWD}\tests\unit\test_data\VW_Template_Overview.pptx:/opt/template/VW_Template_Overview.pptx:ro" `
  -e S3_ENABLED=false `
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

### Send email Lambda (ZIP)

Function `vw-autoreport-sendemail`: Python 3.11, x86_64, handler
`lambda_function.lambda_handler`. Put the files of `functions/vw-autoreport-sendemail`
at the ZIP root. boto3 comes from the Lambda runtime and `pyodbc` from the layer. Use at
least 1024 MB memory and a timeout of about 180 seconds; files up to Microsoft Graph's
150 MB attachment limit are held in memory.

`lambda_handler` handles one recipient and calls the helpers in this order:

1. Checks that the event has `recipient` and `recipient_id`.
2. SSM `/AutoReport/<ACCOUNT>/tenant_id`, `client_id`, `client_secret`, `sender_email`.
3. `get_token`, reads `s3_key` from `REPORT_BUCKET`, then `send_email`. Files below 3 MB
   use Graph `sendMail` directly; larger files use a draft, an upload session in 3 MB
   chunks and then send the draft.
4. `reset_recipientlist`: `send_now = 0` for `recipient_id`.
5. `finish_run`: status `sent` in `T_Control_Autoreport_Runs` for `recipient_id` and `run_id`.
6. `delete_file`: deletes the event's `bucket`/`s3_key`.

If the event is incomplete or sending fails, `finish_run` writes `failed` when
`recipient_id` is known, `send_now` and the report stay, and the error is raised. If the
database update fails after the mail was sent, the error is raised and the report is
kept; `send_now` may then still be `1`, so check the row before the next poll.

Environment variables:

| Variable | Required | Purpose |
|---|---|---|
| `ACCOUNT` | yes | SSM path part, e.g. `Prod` for `/AutoReport/Prod/client_secret` |
| `REPORT_BUCKET` | yes | Bucket of the generated reports |
| `REPORT_PARAM` | yes | SSM parameter with `Server=..;Initial Catalog=..;User ID=..;Password=..` |
| `TIME_OUT` | no | SQL Server timeout in seconds, default `100` |
| `ODBC_DRIVER` | no | Default `ODBC Driver 17 for SQL Server`; must match the layer |
| `AUTOREPORT_SCHEMA` | no | Schema of the control tables, default `control` |

Step Functions Map item:

```json
{
  "StartAt": "Render",
  "States": {
    "Render": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {"FunctionName": "<render-lambda-arn>", "Payload.$": "$"},
      "OutputPath": "$.Payload",
      "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "RenderFailed"}],
      "Next": "SendEmail"
    },
    "SendEmail": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {"FunctionName": "<vw-autoreport-sendemail-arn>", "Payload.$": "$"},
      "OutputPath": "$.Payload",
      "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "SendFailed"}],
      "End": true
    },
    "RenderFailed": {"Type": "Pass", "End": true},
    "SendFailed": {"Type": "Pass", "End": true}
  }
}
```

Do not configure automatic retries for `SendEmail`: a network error on the final Graph
send call can mean the mail was delivered, so a retry could send it twice. Render writes
its own `failed` status, so no separate record step is needed.

Microsoft Graph:

- Grant the app registration application permissions `Mail.Send` and `Mail.ReadWrite`.
  `Mail.ReadWrite` is required for drafts and large-attachment upload sessions.
- Restrict the app to the configured sender mailbox. Exchange Online RBAC for Applications
  is the recommended mechanism; unscoped tenant-wide Entra grants are not restricted by
  it. An Exchange administrator can create a scope and assign
  `Application Mail.Send` and `Application Mail.ReadWrite` to the service principal, then
  verify it:

  ```powershell
  New-ServicePrincipal -AppId <app-id> -ObjectId <enterprise-app-object-id> -DisplayName "VW Autoreport sender"
  New-ManagementScope -Name "VW Autoreport sender" -RecipientRestrictionFilter "PrimarySmtpAddress -eq '<sender@example.com>'"
  New-ManagementRoleAssignment -App <enterprise-app-object-id> -Role "Application Mail.Send" -CustomResourceScope "VW Autoreport sender"
  New-ManagementRoleAssignment -App <enterprise-app-object-id> -Role "Application Mail.ReadWrite" -CustomResourceScope "VW Autoreport sender"
  Test-ServicePrincipalAuthorization -Identity <enterprise-app-object-id> -Resource <sender@example.com>
  ```

- Exchange size limits can be lower than Graph's 150 MB attachment limit.

Networking and IAM:

- Put the Lambda in private subnets that can reach SQL Server on its port.
- Provide outbound HTTPS to `login.microsoftonline.com`, `graph.microsoft.com` and
  `outlook.office.com` through NAT or the corporate egress path.
- Provide access to SSM and S3 through NAT or VPC endpoints. Interface endpoints for SSM
  and KMS, plus an S3 gateway endpoint, are suitable when NAT is not used for AWS APIs.
- Attach `AWSLambdaVPCAccessExecutionRole` (or equivalent ENI and CloudWatch Logs
  permissions), plus:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": [
        "arn:aws:ssm:<region>:<account>:parameter/AutoReport/<ACCOUNT>/tenant_id",
        "arn:aws:ssm:<region>:<account>:parameter/AutoReport/<ACCOUNT>/client_id",
        "arn:aws:ssm:<region>:<account>:parameter/AutoReport/<ACCOUNT>/client_secret",
        "arn:aws:ssm:<region>:<account>:parameter/AutoReport/<ACCOUNT>/sender_email",
        "arn:aws:ssm:<region>:<account>:parameter/<REPORT_PARAM>"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "arn:aws:kms:<region>:<account>:key/<ssm-key-id>"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::<REPORT_BUCKET>/<REPORT_PREFIX>/*.pptx"
    }
  ]
}
```

The database login needs `UPDATE` on `[control].[T_Control_Autoreport_Recipients]` and
`[control].[T_Control_Autoreport_Runs]`. For the default AWS-managed SSM key,
`kms:Decrypt` may not need a separate statement.

ODBC layer:

- The layer must provide `pyodbc` built for Python 3.11 x86_64, unixODBC
  (`libodbc.so.2`), the Microsoft ODBC driver and their native dependencies. Its driver
  name must match `ODBC_DRIVER`.
- If the layer stores `odbcinst.ini` in `/opt/etc`, set `ODBCSYSINI=/opt/etc`; the
  `Driver=` path inside it must point to the driver under `/opt`.
- Libraries under `/opt/lib` are loaded automatically. Set `LD_LIBRARY_PATH` only for a
  different layout.
- Test with a connection before enabling mail.

S3 lifecycle rule as a cleanup safety net:

```json
{
  "Rules": [
    {
      "ID": "ExpireGeneratedAutoreports",
      "Status": "Enabled",
      "Filter": {"Prefix": "reports/"},
      "Expiration": {"Days": 7}
    }
  ]
}
```

`put-bucket-lifecycle-configuration` replaces the bucket's whole lifecycle
configuration. Merge this rule with existing rules before applying it. Never place
templates below the expiring prefix.

## Template contract

- Only `doughnut` charts are supported (`pptcreator/models/enum.py`).
- Chart rows are `{"category": ..., "value": ...}` dicts (first key category, second value).
- Shapes are matched by name suffix: `"<object> Chart"`, `"<object> Headline"`,
  `"<object> Box"`, `"<object> Total"`; a shape named exactly `Legend` is the slide legend.
- Template slide 1 must hold exactly two charts (reference, current); template slide 2
  holds the commodity slots and is repeated when a brand has more commodities than slots.
- Other non-empty text boxes (e.g. `Targets` and the data source line) are copied as is,
  with `{brand}`, `{week}` (current week), `{laufkennung}` (the current snapshot's
  `LAUFKENNUNG`, e.g. `V01-B`), `{datenquelle_run}` (current run as
  `LAUFKENNUNG (LAUF_KW)`, e.g. `V01-B (46/2025)`; the week label if the run is unknown) and
  `{target_label1|2}` / `{target_text1|2}` (empty for now) filled in. Unknown
  placeholders stay visible. Empty boxes such as `Chart 2 Status` are not rendered.
- `{footnote}` holds the brand's `footnote_text` from
  `control.T_Control_Autoreport_BrandFeatures`. It is always substituted: a brand without
  the feature gets an empty string and the shape is removed from the output slide, so no
  literal `{footnote}` and no empty text box ever reaches the deck. Put the token on the
  slides the footnote should appear on; it is currently on slide 2 only.
- `{kpi_explanation}` holds the KPI's `explanation_text` from
  `control.T_Control_Autoreport_KpiMetrics` on overview and COM slides, prefixed with
  `* `. Metric or average values on those charts then end with `*` (e.g. `45 %*`);
  `-` and BKA-count fallbacks are not marked. Put the token on both template slides.
  For KPIs without a text, the shape is removed.
- Put `{showed_Bkas}` in place of `alle BKAs` in the data source text on both template
  slides. It is filled from the KPI metric's `showed_bkas`; a missing, empty or inactive
  metric defaults to `alle BKAs`. Script 008 sets `alle BKAs mit roten Wochen` for
  `rote_bka` and `alle BKAs mit UVB Fehlern` for `uvb_fehlercode`, without overwriting
  existing text. This wording does not change the underlying data filters.
- S3-backed templates are downloaded for each report, so replacing a template in S3
  also updates subsequent reports in warm Lambda environments.
