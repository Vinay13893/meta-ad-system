"""
Email delivery for the daily brief.

Uses Gmail SMTP with an App Password (not your regular Gmail password).
To get an App Password:
  1. Enable 2-Step Verification on your Google account
  2. Go to myaccount.google.com/apppasswords
  3. Create an app password for "Mail" → copy the 16-char password
  4. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env / GitHub secrets
"""
from __future__ import annotations

import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_brief_email(subject: str, body: str) -> None:
    sender   = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ.get("BRIEF_RECIPIENT_EMAIL", sender)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = recipient

    # Plain text part
    msg.attach(MIMEText(body, "plain"))

    # Simple HTML version with monospace font for alignment
    html_body = (
        "<html><body>"
        f"<pre style='font-family:monospace;font-size:14px;line-height:1.5'>{body}</pre>"
        "</body></html>"
    )
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())

    print(f"  Brief emailed to {recipient}")


def send_daily_brief(target_date: date, brief_text: str) -> None:
    subject = f"Daily Brief — Sage Royal Ayurveda — {target_date.strftime('%d %b %Y')}"
    send_brief_email(subject, brief_text)
