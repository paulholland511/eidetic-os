#!/usr/bin/env python3
"""
Atlas OS Email Sender — sends email via SMTP (e.g. Gmail) with optional
attachments.

This is a TEMPLATE. It contains NO credentials. The SMTP app password is read
from the SMTP_APP_PASSWORD environment variable; the sender address and SMTP
server are configurable via environment variables too. Nothing is hardcoded.

For Gmail, generate an app password at
https://myaccount.google.com/apppasswords (requires 2FA), then export it:

    export SMTP_APP_PASSWORD="your-16-char-app-password"
    export SENDER_EMAIL="your-atlas-account@example.com"

Environment variables:
    SMTP_APP_PASSWORD   App password / SMTP password   (required)
    SENDER_EMAIL        From address                   (required)
    SENDER_NAME         Display name                   (default: Atlas)
    SMTP_SERVER         SMTP host                      (default: smtp.gmail.com)
    SMTP_PORT           SMTP port                      (default: 587)

Usage:
    python send_email.py '{"to":"someone@example.com","subject":"Hi",
                           "body_html":"<p>Hello</p>","attachments":["/path/file.pdf"]}'
"""
import json
import os
import smtplib
import sys
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SENDER_NAME = os.environ.get("SENDER_NAME", "Atlas")


def get_app_password() -> str:
    """Read the SMTP app password from the environment. Never hardcode secrets."""
    password = os.environ.get("SMTP_APP_PASSWORD", "").strip()
    if not password:
        print("ERROR: SMTP_APP_PASSWORD environment variable is not set.")
        print("To set up (Gmail):")
        print("  1. Go to https://myaccount.google.com/apppasswords")
        print("  2. Generate an app password for 'Mail'")
        print("  3. export SMTP_APP_PASSWORD='your-app-password'")
        sys.exit(1)
    return password


def send_email(to, subject, body_html=None, body_text=None, attachments=None) -> bool:
    """Send an email via SMTP with STARTTLS."""
    if not SENDER_EMAIL:
        print("ERROR: SENDER_EMAIL environment variable is not set.")
        sys.exit(1)

    app_password = get_app_password()

    msg = MIMEMultipart("mixed")
    msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"] = to if isinstance(to, str) else ", ".join(to)
    msg["Subject"] = subject

    alt = MIMEMultipart("alternative")
    if body_text:
        alt.attach(MIMEText(body_text, "plain"))
    if body_html:
        alt.attach(MIMEText(body_html, "html"))
    elif body_text:
        alt.attach(MIMEText(body_text, "plain"))
    msg.attach(alt)

    if attachments:
        for filepath in attachments:
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{os.path.basename(filepath)}"',
                )
                msg.attach(part)
            else:
                print(f"WARNING: Attachment not found: {filepath}")

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, app_password)
        recipients = [to] if isinstance(to, str) else to
        server.sendmail(SENDER_EMAIL, recipients, msg.as_string())
        server.quit()
        print(f"Email sent successfully to {msg['To']}")
        return True
    except Exception as e:
        print(f"ERROR sending email: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        data = json.loads(sys.argv[1])
        send_email(
            to=data["to"],
            subject=data["subject"],
            body_html=data.get("body_html"),
            body_text=data.get("body_text"),
            attachments=data.get("attachments"),
        )
    else:
        print(
            'Usage: python send_email.py \'{"to":"someone@example.com",'
            '"subject":"sub","body_html":"<p>content</p>",'
            '"attachments":["/path/file.pdf"]}\''
        )
