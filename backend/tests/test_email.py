from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.services.email import (
    EmailRecipient,
    PanicChangeEmail,
    ScheduledIntentEmail,
    _build_message,
    _build_panic_message,
    send_panic_change_email,
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

    def test_builds_panic_change_from_the_same_email_template_system(self) -> None:
        message = _build_panic_message(
            EmailRecipient(email="marko@example.com", first_name="Marko"),
            PanicChangeEmail(
                domain_name="example.com",
                requested_by="Ana Jovanović",
                request_id="panic-request-001",
                operation="CANCEL_COMMIT",
                required_quorum=3,
                expires_at=self.notification.matures_at,
            ),
        )

        self.assertIn("Panic request created", message["Subject"])
        self.assertIn("Hello Marko", message.get_body(("plain",)).get_content())
        html = message.get_body(("html",)).get_content()
        self.assertIn("An emergency DNS change was requested", html)
        self.assertIn("Cancel Commit", html)
        self.assertIn("panic-request-001", html)

    @patch("app.services.email.smtplib.SMTP")
    def test_sends_panic_creation_email_to_every_recipient(
        self, smtp_class: MagicMock
    ) -> None:
        smtp = smtp_class.return_value.__enter__.return_value
        recipients = [
            EmailRecipient(email="creator@example.com", first_name="Ana"),
            EmailRecipient(email="member@example.com", first_name="Marko"),
        ]
        notification = PanicChangeEmail(
            domain_name="example.com",
            requested_by="Ana Jovanović",
            request_id="panic-request-001",
            operation="CANCEL_COMMIT",
            required_quorum=3,
            expires_at=self.notification.matures_at,
        )

        send_panic_change_email(recipients, notification)

        self.assertEqual(smtp.send_message.call_count, 2)
        messages = [call.args[0] for call in smtp.send_message.call_args_list]
        self.assertEqual(
            [message["To"] for message in messages],
            ["creator@example.com", "member@example.com"],
        )

    @patch("app.services.email.smtplib.SMTP")
    def test_skips_demo_addresses_and_logs_that_they_cannot_be_delivered(
        self, smtp_class: MagicMock
    ) -> None:
        smtp = smtp_class.return_value.__enter__.return_value
        recipients = [
            EmailRecipient(email="andrej@gmail.com", first_name="Andrej"),
            EmailRecipient(email="marko@dnsintent.test", first_name="Marko"),
        ]

        with self.assertLogs("app.services.email", level="WARNING") as logs:
            send_scheduled_intent_email(recipients, self.notification)

        smtp.send_message.assert_called_once()
        sent_message = smtp.send_message.call_args.args[0]
        self.assertEqual(sent_message["To"], "andrej@gmail.com")
        self.assertIn("marko@dnsintent.test", " ".join(logs.output))
        self.assertIn("not deliverable", " ".join(logs.output))

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
