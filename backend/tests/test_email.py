from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.services.email import (
    EmailRecipient,
    ScheduledIntentEmail,
    _build_message,
    send_scheduled_intent_email,
)


class ScheduledIntentEmailTests(TestCase):
    def setUp(self) -> None:
        self.original_settings = {
            "smtp_host": settings.smtp_host,
            "smtp_port": settings.smtp_port,
            "smtp_username": settings.smtp_username,
            "smtp_password": settings.smtp_password,
            "smtp_from_email": settings.smtp_from_email,
            "smtp_from_name": settings.smtp_from_name,
        }
        settings.smtp_host = "smtp.gmail.com"
        settings.smtp_port = 587
        settings.smtp_username = "sender@gmail.com"
        settings.smtp_password = "app-password"
        settings.smtp_from_email = "sender@gmail.com"
        settings.smtp_from_name = "DNS Intent"
        now = datetime(2026, 10, 31, 12, 30, tzinfo=timezone.utc)
        self.notification = ScheduledIntentEmail(
            domain_name="example.com",
            scheduled_by="Ana Jovanović",
            commit_hash="A" * 44,
            received_at=now,
            matures_at=now,
        )

    def tearDown(self) -> None:
        for name, value in self.original_settings.items():
            setattr(settings, name, value)

    def test_builds_plain_and_html_message_in_app_style(self) -> None:
        message = _build_message(
            EmailRecipient(email="marko@example.com", first_name="Marko"),
            self.notification,
        )

        self.assertEqual(message["To"], "marko@example.com")
        self.assertIn("example.com", message["Subject"])
        self.assertIn("Hello Marko", message.get_body(("plain",)).get_content())
        html = message.get_body(("html",)).get_content()
        self.assertIn("#102f28", html)
        self.assertIn("#9fe3bd", html)
        self.assertIn("A new protected change was scheduled", html)
        self.assertNotIn("<a ", html)

    @patch("app.services.email.smtplib.SMTP")
    def test_uses_starttls_and_sends_a_private_message_to_each_recipient(
        self, smtp_class: MagicMock
    ) -> None:
        smtp = smtp_class.return_value.__enter__.return_value
        recipients = [
            EmailRecipient(email="ana@example.com", first_name="Ana"),
            EmailRecipient(email="marko@example.com", first_name="Marko"),
        ]

        send_scheduled_intent_email(recipients, self.notification)

        smtp_class.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("sender@gmail.com", "app-password")
        self.assertEqual(smtp.send_message.call_count, 2)
        messages = [call.args[0] for call in smtp.send_message.call_args_list]
        self.assertEqual(
            [message["To"] for message in messages],
            ["ana@example.com", "marko@example.com"],
        )

    @patch("app.services.email.smtplib.SMTP")
    def test_skips_sending_when_credentials_are_missing(
        self, smtp_class: MagicMock
    ) -> None:
        settings.smtp_password = ""

        send_scheduled_intent_email(
            [EmailRecipient(email="ana@example.com", first_name="Ana")],
            self.notification,
        )

        smtp_class.assert_not_called()
