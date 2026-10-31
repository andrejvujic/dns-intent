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
NON_DELIVERABLE_DOMAINS = (".test", ".invalid", ".localhost")


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


@dataclass(frozen=True)
class PanicChangeEmail:
    domain_name: str
    requested_by: str
    request_id: str
    operation: str
    required_quorum: int
    expires_at: datetime
    applied_immediately: bool = False


def _deliverable_recipients(
    recipients: list[EmailRecipient], notification_name: str
) -> list[EmailRecipient]:
    deliverable: list[EmailRecipient] = []
    for recipient in recipients:
        address = recipient.email.strip()
        domain = address.rpartition("@")[2].lower()
        if not domain or domain.endswith(NON_DELIVERABLE_DOMAINS):
            logger.warning(
                "Cannot send %s email to %s: the address is not deliverable.",
                notification_name,
                recipient.email,
            )
            continue
        deliverable.append(
            EmailRecipient(email=address, first_name=recipient.first_name)
        )
    return deliverable


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


def _build_panic_message(
    recipient: EmailRecipient, notification: PanicChangeEmail
) -> EmailMessage:
    domain_name = escape(notification.domain_name)
    first_name = escape(recipient.first_name)
    requested_by = escape(notification.requested_by)
    request_id = escape(notification.request_id)
    operation = escape(notification.operation.replace("_", " ").title())
    expires_at = _format_utc(notification.expires_at)
    applied = notification.applied_immediately
    state_title = "Panic change applied" if applied else "Panic request created"
    headline = (
        "An emergency DNS change was applied"
        if applied
        else "An emergency DNS change was requested"
    )
    explanation = (
        "The request author's vote satisfied the configured quorum, so the change was applied immediately."
        if applied
        else "The request is now pending. Eligible domain members can review the exact change and vote before it expires."
    )
    message = EmailMessage()
    message["Subject"] = f"[DNS Intent] {state_title} for {notification.domain_name}"
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
    message["To"] = recipient.email
    message.set_content(
        f"""Hello {recipient.first_name},

{headline} for {notification.domain_name}.

Requested by: {notification.requested_by}
Operation: {notification.operation}
Request ID: {notification.request_id}
Required quorum: {notification.required_quorum}
Expires at: {expires_at}

{explanation}
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
          <tr><td style="padding:28px 32px;background:#102f28;color:#f7faf8;"><table role="presentation" cellspacing="0" cellpadding="0"><tr><td style="width:46px;height:46px;text-align:center;border-radius:13px;background:#9fe3bd;color:#102f28;font-size:16px;font-weight:800;">DI</td><td style="padding-left:14px;font-size:20px;font-weight:750;">DNS Intent</td></tr></table></td></tr>
          <tr><td style="padding:36px 32px;">
            <p style="margin:0 0 12px;color:#a65349;font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;">{state_title}</p>
            <h1 style="margin:0 0 18px;font-size:28px;line-height:1.2;letter-spacing:-.03em;">{headline}</h1>
            <p style="margin:0 0 26px;color:#68746f;font-size:16px;line-height:1.65;">Hello {first_name}. A panic change was submitted for <strong style="color:#17211e;">{domain_name}</strong>. {explanation}</p>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;background:#f7faf8;border:1px solid #e3ebe6;border-radius:12px;">
              <tr><td style="padding:14px 18px;color:#68746f;font-size:13px;border-bottom:1px solid #e3ebe6;">Requested by</td><td align="right" style="padding:14px 18px;font-size:14px;font-weight:700;border-bottom:1px solid #e3ebe6;">{requested_by}</td></tr>
              <tr><td style="padding:14px 18px;color:#68746f;font-size:13px;border-bottom:1px solid #e3ebe6;">Operation</td><td align="right" style="padding:14px 18px;font-size:14px;font-weight:700;border-bottom:1px solid #e3ebe6;">{operation}</td></tr>
              <tr><td style="padding:14px 18px;color:#68746f;font-size:13px;border-bottom:1px solid #e3ebe6;">Required quorum</td><td align="right" style="padding:14px 18px;font-size:14px;border-bottom:1px solid #e3ebe6;">{notification.required_quorum}</td></tr>
              <tr><td style="padding:14px 18px;color:#68746f;font-size:13px;">Expires</td><td align="right" style="padding:14px 18px;font-size:14px;font-weight:700;">{expires_at}</td></tr>
            </table>
            <p style="margin:24px 0 8px;color:#68746f;font-size:13px;font-weight:700;">REQUEST ID</p>
            <p style="margin:0;padding:14px 16px;border-radius:10px;background:#102f28;color:#c8f1d8;font-family:Consolas,Monaco,monospace;font-size:12px;word-break:break-all;">{request_id}</p>
          </td></tr>
          <tr><td style="padding:22px 32px;background:#edf3ef;color:#68746f;font-size:12px;line-height:1.6;">This is an automated security notification from DNS Intent.</td></tr>
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
    recipients = _deliverable_recipients(recipients, "scheduled-intent")
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
            if settings.smtp_starttls:
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(settings.smtp_username, settings.smtp_password)
            for recipient in recipients:
                try:
                    smtp.send_message(_build_message(recipient, notification))
                    logger.info(
                        "Scheduled-intent email was accepted for %s.", recipient.email
                    )
                except (OSError, smtplib.SMTPException):
                    logger.exception(
                        "Could not send scheduled-intent email to %s.", recipient.email
                    )
    except (OSError, smtplib.SMTPException):
        logger.exception(
            "Could not connect to SMTP while notifying users about intent %s.",
            notification.commit_hash,
        )


def send_panic_change_email(
    recipients: list[EmailRecipient], notification: PanicChangeEmail
) -> None:
    """Send a personalized panic-change message through the shared SMTP setup."""
    recipients = _deliverable_recipients(recipients, "panic-request")
    if not recipients:
        return
    if not settings.smtp_configured:
        logger.warning(
            "Panic request %s was created, but email was skipped because SMTP is not configured.",
            notification.request_id,
        )
        return
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            if settings.smtp_starttls:
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(settings.smtp_username, settings.smtp_password)
            for recipient in recipients:
                try:
                    smtp.send_message(_build_panic_message(recipient, notification))
                    logger.info(
                        "Panic-request email was accepted for %s.", recipient.email
                    )
                except (OSError, smtplib.SMTPException):
                    logger.exception("Could not send panic-change email to %s.", recipient.email)
    except (OSError, smtplib.SMTPException):
        logger.exception(
            "Could not connect to SMTP while notifying users about panic request %s.",
            notification.request_id,
        )
