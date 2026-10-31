import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings


logger = logging.getLogger(__name__)


def notify_users(recipients: list[str], subject: str, body: str) -> None:
    recipients = sorted(set(address for address in recipients if address))
    if not recipients:
        return
    if not settings.smtp_host:
        logger.warning("Email notification (console fallback) to %s: %s\n%s", ", ".join(recipients), subject, body)
        return

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_starttls:
                client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password or "")
            client.send_message(message)
    except (OSError, smtplib.SMTPException):
        logger.exception("Could not send DNSIntent email notification")
