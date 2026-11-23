import json
import os
import uuid

import boto3
import pyodbc as pdb


def lambda_handler(event, context):
    ssm_client = boto3.client("ssm")

    state_machine_arn = os.environ.get("STATE_MACHINE_ARN")
    time_out = int(os.environ.get("TIME_OUT"))
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

            execution_arn = start_state_machine(
                state_machine_arn, run_id, state_machine_input
            )

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
    identical one (email, brand, report_week, comparison_week) is processing or rendered.
    Resolve the current-week selection once for both the duplicate check and render input.
    """
    cursor = report_conn.cursor()
    cursor.execute("""
        SELECT TOP(1) LAUFKENNUNG, LAUF_KW
        FROM [ReportDB].[dbo].[T_RESULT_Leitstand_Overview]
        WHERE AnalyseZeitpunkt = (
            SELECT MAX(AnalyseZeitpunkt)
            FROM [ReportDB].[dbo].[T_RESULT_Leitstand_Overview]
        )
        """)
    row_data = cursor.fetchone()
    latest_run = None
    if row_data:
        run = (row_data[0] or "").strip()
        week = (row_data[1] or "").strip()
        if run and week:
            latest_run = f"{run} ({week})"

    cursor.execute(
        """
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
              WHERE run.status IN ('processing', 'rendered')
                AND LOWER(LTRIM(RTRIM(run.recipients))) = LOWER(LTRIM(RTRIM(r.email)))
                AND run.brand = b.filter_value
                AND run.current_period = CASE
                    WHEN LTRIM(RTRIM(r.report_week)) = 'Aktuelle Woche'
                      OR LTRIM(RTRIM(r.report_week)) LIKE 'Aktuelle Woche%' THEN ?
                    ELSE LTRIM(RTRIM(r.report_week))
                END
                AND run.reference_period = LTRIM(RTRIM(r.comparison_week))
          )
        ORDER BY r.id
        """,
        (latest_run,),
    )
    columns = [column[0] for column in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.close()

    recipients = []
    seen = set()
    for row in rows:
        email = (row["email"] or "").strip()
        report_week = (row["report_week"] or "").strip()
        if is_current_week_selection(report_week):
            if latest_run is None:
                raise ValueError(
                    "No valid latest snapshot available for Aktuelle Woche."
                )
            report_week = latest_run
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


def is_current_week_selection(report_week: str) -> bool:
    return report_week.startswith("Aktuelle Woche")


def start_runs(report_conn: object, run_id: str, recipients: list[dict]) -> None:
    cursor = report_conn.cursor()
    try:
        for recipient in recipients:
            cursor.execute(
                """
                INSERT INTO control.T_Control_Autoreport_Runs
                    (run_id, template_id, recipients, recipient_id, brand,
                     current_period, reference_period, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'processing', SYSUTCDATETIME(), SYSUTCDATETIME())
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
