# Lambda container image for the VW Autoreport.
#
# Build (from the repository root):
#   docker build -f deployment/Dockerfile --secret id=azure_pat,env=AZURE_DEVOPS_PAT -t vw-autoreport .
#
# The private pycore dependency is fetched from Azure DevOps; the PAT is passed as a
# BuildKit secret and never stored in a layer.

# ---------------------------------------------------------------------------- #
# Stage 1: base runtime with the SQL Server ODBC driver
# ---------------------------------------------------------------------------- #
FROM public.ecr.aws/lambda/python:3.12 AS base

# pycore imports pyodbc unconditionally and the LOCAL resource mode talks to the DQN
# SQL Server through "ODBC Driver 18 for SQL Server".
RUN dnf install -y unixODBC unixODBC-devel gcc gcc-c++ git tar gzip \
    && curl -sSL -o /etc/yum.repos.d/mssql-release.repo https://packages.microsoft.com/config/rhel/9/prod.repo \
    && ACCEPT_EULA=Y dnf install -y msodbcsql18 \
    && dnf clean all \
    && odbcinst -q -d

# ---------------------------------------------------------------------------- #
# Stage 2: resolve the dependency list from poetry.lock
# ---------------------------------------------------------------------------- #
FROM base AS deps

COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir "poetry>=1.8,<2" poetry-plugin-export \
    && poetry export --without-hashes --only main -f requirements.txt -o requirements.txt

# pycore comes from a private git repo: inject the PAT at install time only
RUN --mount=type=secret,id=azure_pat \
    PAT="$(cat /run/secrets/azure_pat 2>/dev/null || true)" \
    && if [ -n "$PAT" ]; then \
         sed -i "s#https://factorynavigator@dev.azure.com#https://pat:${PAT}@dev.azure.com#" requirements.txt; \
       fi \
    && pip install --no-cache-dir -r requirements.txt \
    && rm -f requirements.txt \
    && python -c "import pycore, pptx, boto3, pyodbc; print('deps ok')"

# poetry is only needed for the export above
RUN pip uninstall -y poetry poetry-plugin-export >/dev/null 2>&1; true

# ---------------------------------------------------------------------------- #
# Stage 3: application
# ---------------------------------------------------------------------------- #
FROM deps AS app

COPY pptcreator ${LAMBDA_TASK_ROOT}/pptcreator

# pycore reads these at import time; the SAM template can override them.
ENV APP_NAME=VwAutoreport \
    RESOURCE_TYPE=LOCAL \
    LOCAL_BLOB_DIR=/tmp/autoreport_data \
    APP_DB_NAME=ReportDB

CMD ["pptcreator.lambda_handler.handler"]
