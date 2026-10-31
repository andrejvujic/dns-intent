from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

from app.core.config import settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailRecipient:
    email: str
    first_name: str


@dataclass(frozen=True)
class ScheduledIntentEmail:
    domain_name: str
    scheduled_by: str
    commit_hash: str
    received_at: datetime
    matures_at: datetime


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%d %b %Y at %H:%M UTC")


def _build_message(
    recipient: EmailRecipient, notification: ScheduledIntentEmail
) -> EmailMessage:
    domain_name = escape(notification.domain_name)
    first_name = escape(recipient.first_name)
    scheduled_by = escape(notification.scheduled_by)
    commit_hash = escape(notification.commit_hash)
    received_at = _format_utc(notification.received_at)
    matures_at = _format_utc(notification.matures_at)
    message = EmailMessage()
    message["Subject"] = (
        f"[DNS Intent] A new intent was scheduled for {notification.domain_name}"
    )
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
    message["To"] = recipient.email
    message.set_content(
        f"""Hello {recipient.first_name},

A new DNS intent was successfully scheduled for {notification.domain_name}.

Scheduled by: {notification.scheduled_by}
Commit hash: {notification.commit_hash}
Scheduled at: {received_at}
Ready for reveal: {matures_at}

This is an automated security notification. The intent itself remains hidden during the holding period.
"""
    )
    message.add_alternative(
        f"""\
<!doctype html>
<html lang="en">
  <body style="margin:0;padding:0;background:#f2f5f2;color:#17211e;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f2f5f2;padding:32px 16px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#ffffff;border:1px solid #dce5df;border-radius:18px;overflow:hidden;">
          <tr>
            <td style="padding:28px 32px;background:#102f28;color:#f7faf8;">
              <table role="presentation" cellspacing="0" cellpadding="0"><tr>
                <td style="width:46px;height:46px;text-align:center;border-radius:13px;background:#9fe3bd;color:#102f28;font-size:16px;font-weight:800;">DI</td>
                <td style="padding-left:14px;font-size:20px;font-weight:750;">DNS Intent</td>
              </tr></table>
            </td>
          </tr>
          <tr>
            <td style="padding:36px 32px;">
              <p style="margin:0 0 12px;color:#3f956a;font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;">Intent scheduled</p>
              <h1 style="margin:0 0 18px;font-size:28px;line-height:1.2;letter-spacing:-.03em;">A new protected change was scheduled</h1>
              <p style="margin:0 0 26px;color:#68746f;font-size:16px;line-height:1.65;">Hello {first_name}, a new DNS intent for <strong style="color:#17211e;">{domain_name}</strong> was successfully received. The holding period has started.</p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;background:#f7faf8;border:1px solid #e3ebe6;border-radius:12px;">
                <tr><td style="padding:16px 18px;color:#68746f;font-size:13px;border-bottom:1px solid #e3ebe6;">Scheduled by</td><td align="right" style="padding:16px 18px;font-size:14px;font-weight:700;border-bottom:1px solid #e3ebe6;">{scheduled_by}</td></tr>
                <tr><td style="padding:16px 18px;color:#68746f;font-size:13px;border-bottom:1px solid #e3ebe6;">Scheduled at</td><td align="right" style="padding:16px 18px;font-size:14px;border-bottom:1px solid #e3ebe6;">{received_at}</td></tr>
                <tr><td style="padding:16px 18px;color:#68746f;font-size:13px;">Ready for reveal</td><td align="right" style="padding:16px 18px;font-size:14px;font-weight:700;color:#184f40;">{matures_at}</td></tr>
              </table>
              <p style="margin:24px 0 8px;color:#68746f;font-size:13px;font-weight:700;">COMMIT HASH</p>
              <p style="margin:0;padding:14px 16px;border-radius:10px;background:#102f28;color:#c8f1d8;font-family:Consolas,Monaco,monospace;font-size:12px;line-height:1.6;word-break:break-all;">{commit_hash}</p>
            </td>
          </tr>
          <tr><td style="padding:22px 32px;background:#edf3ef;color:#68746f;font-size:12px;line-height:1.6;">This is an automated security notification. The intent itself remains hidden during the holding period.</td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
""",
        subtype="html",
    )
    return message


def send_scheduled_intent_email(
    recipients: list[EmailRecipient], notification: ScheduledIntentEmail
) -> None:
    """Send one personalized message per recipient without exposing addresses."""
    if not recipients:
        return
    if not settings.smtp_configured:
        logger.warning(
            "Intent %s was scheduled, but email was skipped because SMTP is not configured.",
            notification.commit_hash,
        )
        return

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(settings.smtp_username, settings.smtp_password)
            for recipient in recipients:
                try:
                    smtp.send_message(_build_message(recipient, notification))
                except (OSError, smtplib.SMTPException):
                    logger.exception(
                        "Could not send scheduled-intent email to %s.", recipient.email
                    )
    except (OSError, smtplib.SMTPException):
        logger.exception(
            "Could not connect to SMTP while notifying users about intent %s.",
            notification.commit_hash,
        )
