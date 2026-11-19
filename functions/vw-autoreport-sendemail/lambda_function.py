import datetime as dt
import html
import json
import os

import boto3
import pyodbc as pdb


from get_token import get_token
from send_email import send_email
from settings import settings


def lambda_handler(event, context):
    ssm_client = boto3.client("ssm")

    account = os.environ["ACCOUNT"]
    report_bucket = os.environ["REPORT_BUCKET"]
    report_prefix = os.environ.get("REPORT_PREFIX", "reports").strip("/")
    reportdb_param = os.environ["REPORT_PARAM"]
    time_out = int(os.environ.get("TIME_OUT", "100"))
    sns_url = os.environ("SNS_URL")

    # Sent by vw-autoreport-render as its Step Functions output: one recipient per call
    recipient = event.get("recipient")
    recipient_id = event.get("recipient_id")
    run_id = event.get("run_id")
    brand = event.get("brand")
    bucket = event.get("bucket")
    s3_key = event.get("s3_key")
    file_name = event.get("file_name")
    print(f"LOG: Report {s3_key} for {brand} received for recipient id {recipient_id}")

    try:
        if not recipient or recipient_id is None:
            raise ValueError("Event needs exactly one recipient and recipient_id")

        tenant_id = get_parameter(ssm_client, f"/AutoReport/{account}/tenant_id")
        client_id = get_parameter(ssm_client, f"/AutoReport/{account}/client_id")
        client_secret = get_parameter(
            ssm_client, f"/AutoReport/{account}/client_secret"
        )
        sender_email = get_parameter(ssm_client, f"/AutoReport/{account}/sender_email")

        # Retrieve email token
        access_token = get_token(tenant_id, client_id, client_secret)
        print("LOG: Token retrieved")

        # Read file from S3
        s3 = boto3.client("s3")
        response = s3.get_object(Bucket=report_bucket, Key=s3_key)
        file_content = response["Body"].read()
        print(f"LOG: File retrieved ({len(file_content)} bytes)")

        # Send email
        send_email(
            [recipient],
            access_token,
            file_content,
            file_name,
            sender_email,
            settings.email_html.format(
                dt.date.today().strftime("%d.%m.%Y"), html.escape(brand)
            ),
            event.get("email_subject")
            or f"IDM Control Center Report für Einkaufsorganisation {brand}",
        )
        print(f"LOG: Email sent successfully to {recipient}")

        # Adjust database
        report_conn = get_pyodbc_connection(ssm_client, reportdb_param, time_out)
        try:
            reset_recipientlist(report_conn, recipient_id)
            finish_run(report_conn, run_id, recipient_id, "sent")
        finally:
            report_conn.close()

        # Delete file from S3
        delete_file(report_bucket, s3_key)

        return {
            "statusCode": 200,
            "body": f"VW-autoreport successfully sent to {recipient}",
        }

    except Exception as e:
        print(f"LOG: Error sending file: {e}")
        mark_run_failed(
            ssm_client, reportdb_param, time_out, run_id, recipient_id, str(e)
        )
        send_alert(sns_url, str(e))
        raise


def get_parameter(ssm_client: object, name: str) -> str:
    return ssm_client.get_parameter(Name=name, WithDecryption=True)["Parameter"][
        "Value"
    ]


def get_pyodbc_connection(
    ssm_client: object, ssm_param_name: str, time_out: int
) -> object:
    """
    Opens a SQL Server connection using a connection string from AWS SSM.
    """
    try:
        connection_string = get_parameter(ssm_client, ssm_param_name)

        values = {}
        for part in connection_string.split(";"):
            key, separator, value = part.partition("=")
            if separator:
                values[key.replace(" ", "").lower()] = value.strip()

        def odbc_value(value: str) -> str:
            return "{" + value.replace("}", "}}") + "}"

        driver = os.environ.get("ODBC_DRIVER", "ODBC Driver 17 for SQL Server")
        parameters = (
            f"DRIVER={{{driver}}};"
            f"SERVER={odbc_value(values['server'])};"
            f"DATABASE={odbc_value(values['initialcatalog'])};"
            f"UID={odbc_value(values['userid'])};"
            f"PWD={odbc_value(values['password'])}"
        )

        connection = pdb.connect(parameters, timeout=time_out)
        connection.timeout = time_out
        return connection

    except Exception as e:
        print(
            f"ERROR: get_pyodbc_connection failed for SSM parameter: {ssm_param_name}"
        )
        print(f"ERROR DETAILS: {type(e).__name__}")
        raise


def reset_recipientlist(report_conn: object, recipient_id: int) -> None:
    """
    Resets send_now for the recipient row of this report.
    """
    try:
        cursor = report_conn.cursor()
        cursor.execute(
            f"UPDATE [{schema()}].[T_Control_Autoreport_Recipients] "
            "SET send_now = 0 WHERE id = ? AND send_now = 1",
            int(recipient_id),
        )
        report_conn.commit()
        cursor.close()
    except Exception as e:
        print(f"ERROR: reset_recipientlist failed for recipient id: {recipient_id}")
        print(f"ERROR DETAILS: {e}")
        raise


def finish_run(
    report_conn: object,
    run_id: str | None,
    recipient_id: int,
    status: str,
    error: str | None = None,
) -> None:
    """
    Writes the final status of this report to the run log.
    """
    statement = (
        f"UPDATE [{schema()}].[T_Control_Autoreport_Runs] "
        "SET status = ?, error = ?, updated_at = SYSUTCDATETIME() "
        "WHERE recipient_id = ?"
    )
    params = [status, error[:4000] if error else None, int(recipient_id)]
    if run_id:
        statement += " AND run_id = ?"
        params.append(run_id)
    try:
        cursor = report_conn.cursor()
        cursor.execute(statement, params)
        report_conn.commit()
        cursor.close()
    except Exception as e:
        print(
            f"ERROR: finish_run failed for run: {run_id}, recipient id: {recipient_id}"
        )
        print(f"ERROR DETAILS: {e}")
        raise


def mark_run_failed(
    ssm_client: object,
    reportdb_param: str,
    time_out: int,
    run_id: str | None,
    recipient_id: int | None,
    error: str,
) -> None:
    # Best effort: the original error is raised by the caller
    if recipient_id is None:
        return
    try:
        report_conn = get_pyodbc_connection(ssm_client, reportdb_param, time_out)
        try:
            finish_run(report_conn, run_id, recipient_id, "failed", error)
        finally:
            report_conn.close()
    except Exception as e:
        print(f"ERROR: Could not mark run as failed: {e}")


def delete_file(bucket: str, s3_key: str) -> None:
    boto3.client("s3").delete_object(Bucket=bucket, Key=s3_key)
    print(f"LOG: Deleted s3://{bucket}/{s3_key}")


def schema() -> str:
    value = os.environ.get("AUTOREPORT_SCHEMA", "control")
    if not value.isidentifier():
        raise ValueError(f"Invalid AUTOREPORT_SCHEMA {value!r}")
    return value


def send_alert(sns_url: str, file_name: str) -> None:
    sns_client = boto3.client("sns")
    response = sns_client.publish(
        TopicArn=sns_url,
        Subject="Data Validation Failure Alert",
        Message=f"Error validating file {file_name}",
    )
    print(f"LOG: Alert sent for file {file_name}, SNS response: {response}")
