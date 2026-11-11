import base64
import json
import logging

import requests
from pycore.easy import storage, vault


def send_email(config_dict: dict) -> None:
    try:
        # Read file
        target_file_name = f"{config_dict['target_file_name']}.pptx"
        target_blob_container = config_dict["target_blob_container"]
        ppt_file = storage.read_blob(
            blob_name=target_file_name,
            container_name=target_blob_container,
            decode=False,
        )

        # Get recepients
        recipients = config_dict["recipients"]
        recipients_list = [
            {"emailAddress": {"address": recipient}} for recipient in recipients
        ]

        # Get bearer token
        sender_user = vault.get_secret("sender_user")
        tenant_id = vault.get_secret("tenant_id")
        client_id = vault.get_secret("client_id")
        client_secret = vault.get_secret("client_secret")

        access_token = get_token(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )

        attachment = {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": target_file_name,
            "contentType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "contentBytes": base64.b64encode(ppt_file).decode("utf-8"),  # type: ignore[arg-type]
        }

        subject = f"Report: {config_dict['target_file_name']}"
        html_body = f"<p>Please find the attached PowerPoint report: <strong>{target_file_name}</strong>.</p>"

        send_via_graph(
            recipients_list=recipients_list,
            subject=subject,
            html_body=html_body,
            access_token=access_token,
            sender_user=sender_user,
            attachment=attachment,
        )
        logging.info(f"PPT email sent to {recipients_list} (file: {target_file_name})")
    except Exception as e:
        logging.exception(f"Failed to send PPT email: {e}")
        raise


def get_token(tenant_id, client_id, client_secret):
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    token_data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }

    token_response = requests.post(token_url, data=token_data)
    token_response.raise_for_status()
    access_token = token_response.json()["access_token"]

    return access_token


def send_via_graph(
    recipients_list: list,
    subject: str,
    html_body: str,
    access_token: str,
    sender_user: str,
    attachment: dict | None = None,
) -> None:

    send_mail_url = f"https://graph.microsoft.com/v1.0/users/{sender_user}/sendMail"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    message: dict = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": html_body},
        "bccRecipients": recipients_list,
    }
    message["attachments"] = [attachment]

    payload = {"message": message, "saveToSentItems": True}
    response = requests.post(
        send_mail_url, headers=headers, data=json.dumps(payload), timeout=60
    )
    response.raise_for_status()
