import base64
import json
import urllib.error
import urllib.parse
import urllib.request

GRAPH_URL = "https://graph.microsoft.com/v1.0"
SMALL_FILE_LIMIT = 3 * 1024 * 1024  # Graph accepts direct attachments only below 3 MB
UPLOAD_CHUNK_SIZE = 3 * 1024 * 1024  # Microsoft recommends chunks below 4 MB


def send_email(
    recipients: list[str],
    access_token: str,
    file: bytes,
    file_name: str,
    sender_user: str,
    email_html: str,
    subject: str,
):
    mailbox_url = f"{GRAPH_URL}/users/{urllib.parse.quote(sender_user, safe='@')}"
    message = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": email_html,
        },
        "bccRecipients": [{"emailAddress": {"address": recipient}} for recipient in recipients],
    }

    if len(file) < SMALL_FILE_LIMIT:
        message["attachments"] = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": file_name,
                "contentBytes": base64.b64encode(file).decode("utf-8"),
            }
        ]
        _request("POST", f"{mailbox_url}/sendMail", 202, access_token, {"message": message, "saveToSentItems": True})
        print("LOG: Email sent successfully!")
        return

    # Files from 3 MB: create a draft, upload the file in chunks, then send the draft
    draft = _request("POST", f"{mailbox_url}/messages", 201, access_token, message)
    message_url = f"{mailbox_url}/messages/{urllib.parse.quote(draft['id'], safe='')}"
    try:
        upload_attachment(access_token, message_url, file, file_name)
    except Exception:
        try:
            _request("DELETE", message_url, 204, access_token)
        except Exception as e:
            print(f"LOG: Could not delete draft: {e}")
        raise

    _request("POST", f"{message_url}/send", 202, access_token)
    print("LOG: Email sent successfully!")


def upload_attachment(access_token: str, message_url: str, file: bytes, file_name: str) -> None:
    session = _request(
        "POST",
        f"{message_url}/attachments/createUploadSession",
        201,
        access_token,
        {"AttachmentItem": {"attachmentType": "file", "name": file_name, "size": len(file)}},
    )

    total = len(file)
    for start in range(0, total, UPLOAD_CHUNK_SIZE):
        chunk = file[start:start + UPLOAD_CHUNK_SIZE]
        end = start + len(chunk) - 1
        # The upload URL contains its own temporary authorization, so no bearer token is sent
        status, content = _open(
            "PUT",
            session["uploadUrl"],
            {"Content-Type": "application/octet-stream", "Content-Range": f"bytes {start}-{end}/{total}"},
            chunk,
        )
        if status not in (200, 201):
            raise RuntimeError(f"Attachment upload failed: {status} {content[:500]!r}")


def _request(method: str, url: str, expected_status: int, access_token: str, body: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    status, content = _open(method, url, headers, data)
    if status != expected_status:
        raise RuntimeError(f"Email sent failed: {status} {content[:500]!r}")
    return json.loads(content) if content else {}


def _open(method: str, url: str, headers: dict, data: bytes | None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
