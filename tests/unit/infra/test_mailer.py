import email

import pytest

from pptcreator.config import settings
from pptcreator.infra import mailer


def test_validate_recipients_dedups_and_rejects_invalid():
    assert mailer.validate_recipients([" a@x.de ", "a@x.de", "b@x.de"]) == ["a@x.de", "b@x.de"]
    with pytest.raises(mailer.MailError):
        mailer.validate_recipients(["not-an-address"])
    with pytest.raises(mailer.MailError):
        mailer.validate_recipients([])


def test_build_message_contains_attachment_and_bodies():
    msg = mailer.build_message(
        sender="s@x.de",
        recipients=["a@x.de"],
        subject="Sub",
        html_body="<p>hi</p>",
        text_body="hi",
        attachment_name="deck.pptx",
        attachment_bytes=b"PK\x03\x04data",
    )
    parsed = email.message_from_bytes(msg.as_bytes())
    parts = {p.get_content_type(): p for p in parsed.walk()}
    assert "text/plain" in parts and "text/html" in parts
    assert mailer.PPTX_MIME in parts
    assert parts[mailer.PPTX_MIME].get_filename() == "deck.pptx"
    assert parts[mailer.PPTX_MIME].get_payload(decode=True) == b"PK\x03\x04data"
    assert parsed["To"] == "undisclosed-recipients:;"  # bcc mode hides recipients
    assert "a@x.de" not in msg.as_bytes().decode("utf-8", "ignore").split("\n\n")[0]


def test_build_message_to_mode():
    msg = mailer.build_message(
        sender="s@x.de",
        recipients=["a@x.de", "b@x.de"],
        subject="Sub",
        html_body="",
        text_body="",
        attachment_name="d.pptx",
        attachment_bytes=b"x",
        recipients_mode="to",
    )
    assert msg["To"] == "a@x.de, b@x.de"


def test_attachment_size_guard(monkeypatch):
    monkeypatch.setattr(settings, "ses_max_attachment_mb", 1)
    with pytest.raises(mailer.MailError, match="above the configured limit"):
        mailer.build_message(
            sender="s@x.de",
            recipients=["a@x.de"],
            subject="",
            html_body="",
            text_body="",
            attachment_name="big.pptx",
            attachment_bytes=b"0" * (2 * 1024 * 1024),
        )


def test_send_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "mail_enabled", False)
    assert (
        mailer.send_pptx(
            recipients=["a@x.de"],
            subject="s",
            html_body="",
            text_body="",
            attachment_name="d.pptx",
            attachment_bytes=b"x",
        )
        is None
    )


def test_send_via_ses(aws):
    message_id = mailer.send_pptx(
        recipients=["a@x.de", "b@x.de"],
        subject="KPI",
        html_body="<p>x</p>",
        text_body="x",
        attachment_name="deck.pptx",
        attachment_bytes=b"PK",
    )
    assert message_id
    quota = aws["ses"].get_send_quota()
    assert quota["SentLast24Hours"] == 2  # one per destination


def test_send_unverified_sender_raises(aws, monkeypatch):
    monkeypatch.setattr(settings, "ses_sender", "unknown@x.de")
    with pytest.raises(mailer.MailError):
        mailer.send_pptx(
            recipients=["a@x.de"],
            subject="",
            html_body="",
            text_body="",
            attachment_name="d.pptx",
            attachment_bytes=b"x",
            max_attempts=1,
        )
