from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


def send_email_with_attachments(
    smtp_host: str,
    smtp_port: int,
    use_tls: bool,
    sender: str,
    password_env_var: str,
    recipients: list[str],
    subject: str,
    html_body: str,
    attachments: list[str | Path],
) -> None:
    password = os.environ.get(password_env_var)
    if not password:
        raise RuntimeError(f"Missing SMTP password in environment variable: {password_env_var}")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content("HTML-capable email required to view this report.")
    msg.add_alternative(html_body, subtype="html")

    for attachment in attachments:
        path = Path(attachment)
        with open(path, "rb") as f:
            data = f.read()
        subtype = "csv" if path.suffix.lower() == ".csv" else "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        maintype = "text" if path.suffix.lower() == ".csv" else "application"
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=60) as server:
        if use_tls:
            server.starttls()
        server.login(sender, password)
        server.send_message(msg)
