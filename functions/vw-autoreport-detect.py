import json
import os
import uuid

import boto3
import pyodbc as pdb


def lambda_handler(event, context):
    ssm_client = boto3.client("ssm")

    state_machine_arn = os.environ.get("STATE_MACHINE_ARN")
    time_out = int(os.environ.get("TIME_OUT", "100"))
    reportdb_param = os.environ.get("REPORT_PARAM")
    sns_url = os.environ.get("SNS_URL")

    try:
        if not state_machine_arn:
            raise ValueError("STATE_MACHINE_ARN is not set")

        report_conn = get_pyodbc_connection(ssm_client, reportdb_param, time_out)
        try:
            # Check if there are new send_now recipients
            recipients = get_new_recipients(report_conn)
            if not recipients:
                print("LOG: No recipients found for send_now.")
                return {"statusCode": 200, "body": "No report request found"}

            print(f"LOG: Found {len(recipients)} recipient(s) for send_now.")
            run_id = str(uuid.uuid4())

            # Start runs in T_Control_Autoreport_Runs, so the next poll skips these rows
            start_runs(report_conn, run_id, recipients)

            # Prepare output in format for state machine and trigger it
            state_machine_input = build_state_machine_input(run_id, recipients)
            try:
                execution_arn = start_state_machine(
                    state_machine_arn, run_id, state_machine_input
                )
            except Exception as e:
                fail_runs(report_conn, run_id, f"State machine start failed: {e}")
                raise
        finally:
            report_conn.close()

        return {
            "statusCode": 200,
            "body": f"Started {execution_arn} for {len(recipients)} recipient(s)",
            "execution_arn": execution_arn,
        }

    except Exception as e:
        print(f"ERROR: vw-autoreport-detect failed: {e}")
        send_alert(sns_url, str(e))
        raise


def get_new_recipients(report_conn: object) -> list[dict]:
    """
    send_now rows of active templates and brands. A request is skipped while an
    identical one (email, brand, report_week, comparison_week) is still processing.
    """
    cursor = report_conn.cursor()
    cursor.execute("""
        SELECT r.id, r.template_id, r.email, b.filter_value AS brand,
               r.report_week, r.comparison_week
        FROM control.T_Control_Autoreport_Recipients r
        JOIN control.T_Control_Autoreport_Templates t
          ON t.id = r.template_id AND t.is_active = 1
        JOIN control.T_Control_Autoreport_Brands b
          ON b.id = r.brand_id AND b.is_active = 1
        WHERE r.send_now = 1
          AND r.IsDeleted = 0
          AND NOT EXISTS (
              SELECT 1
              FROM control.T_Control_Autoreport_Runs run
              WHERE run.status = 'processing'
                AND LOWER(LTRIM(RTRIM(run.user_email))) = LOWER(LTRIM(RTRIM(r.email)))
                AND run.brand = b.filter_value
                AND run.primary_date = LTRIM(RTRIM(r.report_week))
                AND run.reference_date = LTRIM(RTRIM(r.comparison_week))
          )
        ORDER BY r.id
        """)
    columns = [column[0] for column in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.close()

    recipients = []
    seen = set()
    for row in rows:
        email = (row["email"] or "").strip()
        report_week = (row["report_week"] or "").strip()
        comparison_week = (row["comparison_week"] or "").strip()
        if (
            not email
            or not report_week
            or not comparison_week
            or report_week == comparison_week
        ):
            print(
                f"WARNING: Recipient {row['id']} skipped: email, report_week or comparison_week invalid"
            )
            continue

        # Identical requests found in this same poll are sent only once
        request_key = (email.lower(), row["brand"], report_week, comparison_week)
        if request_key in seen:
            print(
                f"WARNING: Recipient {row['id']} skipped: identical request is already in this run"
            )
            continue
        seen.add(request_key)

        recipients.append(
            {
                "id": int(row["id"]),
                "template_id": int(row["template_id"]),
                "email": email,
                "brand": row["brand"],
                "report_week": report_week,
                "comparison_week": comparison_week,
            }
        )
    return recipients


def start_runs(report_conn: object, run_id: str, recipients: list[dict]) -> None:
    cursor = report_conn.cursor()
    try:
        for recipient in recipients:
            cursor.execute(
                """
                INSERT INTO control.T_Control_Autoreport_Runs
                    (run_id, template_id, user_email, recipient_id, brand,
                     primary_date, reference_date, [trigger], status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'adhoc', 'processing', SYSUTCDATETIME(), SYSUTCDATETIME())
                """,
                (
                    run_id,
                    recipient["template_id"],
                    recipient["email"],
                    recipient["id"],
                    recipient["brand"],
                    recipient["report_week"],
                    recipient["comparison_week"],
                ),
            )
        report_conn.commit()
    except Exception:
        report_conn.rollback()
        raise
    finally:
        cursor.close()
    print(
        f"LOG: Started run {run_id} for recipient ids {[r['id'] for r in recipients]}"
    )


def build_state_machine_input(run_id: str, recipients: list[dict]) -> dict:
    """
    Same format as the former plan Lambda; the state machine maps over "requests".
    """
    requests = [
        {
            "template_id": recipient["template_id"],
            "brand": recipient["brand"],
            "current_period": recipient["report_week"],
            "reference_period": recipient["comparison_week"],
            "recipients": [recipient["email"]],
            "recipient_ids": [recipient["id"]],
            "run_id": run_id,
        }
        for recipient in recipients
    ]
    return {
        "has_requests": bool(requests),
        "count": len(requests),
        "requests": requests,
    }


def start_state_machine(
    state_machine_arn: str, run_id: str, state_machine_input: dict
) -> str:
    response = boto3.client("stepfunctions").start_execution(
        stateMachineArn=state_machine_arn,
        name=run_id,
        input=json.dumps(state_machine_input),
    )
    print(f"LOG: Started state machine execution {response['executionArn']}")
    return response["executionArn"]


def fail_runs(report_conn: object, run_id: str, error: str) -> None:
    """
    Closes the claims of this run; send_now stays 1, so the next poll retries.
    """
    cursor = report_conn.cursor()
    cursor.execute(
        """
        UPDATE control.T_Control_Autoreport_Runs
        SET status = 'failed', error = ?, updated_at = SYSUTCDATETIME()
        WHERE run_id = ? AND status = 'processing'
        """,
        (error[:4000], run_id),
    )
    report_conn.commit()
    cursor.close()
    print(f"LOG: Marked run {run_id} as failed")


def get_pyodbc_connection(
    ssm_client: object, ssm_param_name: str, time_out: int
) -> object:
    """
    Opens a SQL Server connection using a connection string from AWS SSM.
    """
    try:
        response = ssm_client.get_parameter(Name=ssm_param_name, WithDecryption=True)
        connection_string = response["Parameter"]["Value"]

        cs = connection_string.replace(" ", "")

        for char in ["=", ";"]:
            cs = cs.replace(char, " ")

        cs = cs.split(" ")

        parameters = (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=" + cs[cs.index("Server") + 1] + ";"
            "DATABASE=" + cs[cs.index("InitialCatalog") + 1] + ";"
            "UID=" + cs[cs.index("UserID") + 1] + ";"
            "PWD=" + cs[cs.index("Password") + 1]
        )

        connection = pdb.connect(parameters, timeout=time_out)
        return connection

    except Exception as e:
        print(
            f"ERROR: get_pyodbc_connection failed for SSM parameter: {ssm_param_name}"
        )
        print(f"ERROR DETAILS: {e}")
        raise


def send_alert(sns_url: str | None, error: str) -> None:
    if not sns_url:
        print("LOG: SNS_URL not set; no alert sent")
        return
    try:
        response = boto3.client("sns").publish(
            TopicArn=sns_url,
            Subject="VW Autoreport detect failed",
            Message=error,
        )
        print(f"LOG: Alert sent, SNS MessageId: {response['MessageId']}")
    except Exception as e:
        print(f"ERROR: Could not send alert: {e}")
