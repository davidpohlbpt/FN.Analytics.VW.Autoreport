# FN.Analytics.VW.Autoreport

Automated PowerPoint KPI reporting for VW, running as an AWS Lambda. For every brand
and reference period requested in the recipient list, a deck with six KPIs (current
week vs. reference week, overall and per commodity) is rendered from the VW template,
stored in S3 and e-mailed via SES.

Built on the internal `pycore` framework (resource mode `LOCAL`: SQL Server via pyodbc,
file storage under `/tmp`, secrets from environment variables). `pycore` is unchanged.

## Pipeline

```
EventBridge (weekly cron) / manual invoke
  -> lambda_handler.handler(event)
       -> steer_scheduled_kpi_decks            (recipient table -> one deck per brand + reference period)
            for each (brand, current, reference)
              -> steer_kpi_deck_process
                   - s3_sync.download_template   (S3 -> pycore storage, cached in /tmp)
                   - get_kpi_deck_config
                       - discover_chart_slots    (template: 2 overview charts, N commodity slots)
                       - KpiSource.fetch         (stub now, DQN KPI table later)
                       - build_output_slides     (6 KPIs x [overview + paginated detail slides])
                       - get_template_config     (.pptx shapes: positions, fonts, legend)
                   - graph_create_ppt            (python-pptx rendering -> pycore storage)
                   - s3_sync.upload_output       (pycore storage -> S3)
                   - send_email                  (SES raw e-mail with .pptx attachment)
```

The legacy per-template pipeline (`graph_steer_creation_process`, control tables,
Config Center) is still present and used by the older tests.

## Lambda events

```json
{"mode": "scheduled", "current_period": "2026-KW45", "reference_period": "2026-KW37"}
{"mode": "manual", "brand": "Audi", "current_period": "KW45", "reference_period": "KW37",
 "recipients": ["you@example.com"], "kpi_ids": ["kpi1"]}
{"mode": "adhoc"}
```

`current_period` defaults to the current ISO week, `reference_period` to eight weeks
before. The response is a summary with one entry per deck (`sent` / `rendered` /
`failed`, S3 key, SES message id, error).

## Configuration

All settings are environment variables (see `.env.example`, `pptcreator/config.py`).
Key switches:

| Variable | Purpose |
|---|---|
| `RESOURCE_TYPE`, `APP_NAME`, `LOCAL_BLOB_DIR`, `LOCAL_SQLSERVER_CONN_STR` | pycore resources |
| `S3_ENABLED`, `S3_BUCKET`, `S3_TEMPLATE_KEY`, `S3_OUTPUT_PREFIX` | template source and report sink |
| `MAIL_ENABLED`, `SES_SENDER`, `SES_RECIPIENTS_MODE` | e-mail |
| `KPI_SOURCE` (`stub` / `sql`) | data source; `sql` is wired once the KPI table schema is known |
| `RECIPIENTS_SCHEMA`, `RECIPIENTS_TABLE` | recipient list (`id, email, brand, reference_timestamp, send_now, is_active, lasteditedat`) |
| `AWS_REGION_NAME` | boto3 region (`AWS_REGION` is reserved in Lambda) |

KPI definitions (titles, palettes, category order) live in `pptcreator/kpi/registry.py`.

## Local development

```powershell
poetry install --with test
Copy-Item .env.example .env   # fill in values
poetry run pytest
poetry run pptcreator manual --brand Audi --reference KW37 --recipient you@example.com
```

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
- `.github/workflows/deploy.yml` -- test, build, push to ECR, `sam deploy` (`main` -> dev,
  tags `v*` -> prod), upload the template to the bucket.

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
- `Status` and `Targets` shapes in the template are currently not rendered.
