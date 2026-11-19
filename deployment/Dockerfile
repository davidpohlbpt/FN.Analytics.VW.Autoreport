FROM public.ecr.aws/lambda/python:3.12

WORKDIR ${LAMBDA_TASK_ROOT}

# ------------------------- ODBC driver for SQL Server ------------------------ #
# pycore imports pyodbc unconditionally and the LOCAL resource mode talks to the DQN
# SQL Server through "ODBC Driver 18 for SQL Server".
RUN dnf install -y unixODBC unixODBC-devel gcc gcc-c++ \
    && curl -sSL -o /etc/yum.repos.d/mssql-release.repo https://packages.microsoft.com/config/rhel/9/prod.repo \
    && ACCEPT_EULA=Y dnf install -y msodbcsql18 \
    && dnf clean all \
    && odbcinst -q -d

# ------------------------------ Python deps ---------------------------------- #
COPY vendor ./vendor
COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt \
    && python -c "import pycore, pptx, boto3, pyodbc; print('deps ok')" \
    && rm -rf ./vendor requirements-docker.txt

# ------------------------- Optional internal CA bundle ----------------------- #
# Place PEM files in deployment/certs/ (e.g. the VW root CA) to make them trusted by
# requests (DQN API) and by the ODBC driver (SQL Server with Encrypt=yes). The folder
# ships with a .gitkeep so the COPY succeeds even when empty.
COPY deployment/certs ./certs
RUN if ls ./certs/*.pem >/dev/null 2>&1; then \
      cat ./certs/*.pem > ./certs/ca-bundle.pem && chmod 644 ./certs/ca-bundle.pem \
      && cp ./certs/*.pem /etc/pki/ca-trust/source/anchors/ \
      && update-ca-trust extract; \
    fi
# Read by pptcreator.lambdas._bootstrap: activates REQUESTS_CA_BUNDLE / SSL_CERT_FILE when the file exists.
# The system trust store above covers the ODBC driver (Encrypt=yes).
ENV CA_BUNDLE_PATH=${LAMBDA_TASK_ROOT}/certs/ca-bundle.pem

# ------------------------------ Application ---------------------------------- #
COPY pptcreator ./pptcreator
RUN chmod -R a+rX ./pptcreator

# pycore reads these at import time; Lambda environment variables override them.
ENV APP_NAME=VwAutoreport \
    RESOURCE_TYPE=LOCAL \
    LOCAL_BLOB_DIR=/tmp/autoreport_data \
    APP_DB_NAME=ReportDB

# Default = Lambda 2 (render). The plan function overrides the command in its Lambda
# image configuration (CMD override): pptcreator.lambdas.plan.handler
# The send Lambda is not part of this image: functions/vw-autoreport-sendemail is a ZIP.
CMD ["pptcreator.lambdas.render.handler"]
