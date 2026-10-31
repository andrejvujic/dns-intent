from datetime import datetime, timedelta, timezone
from unittest import TestCase

from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes.domains import apply_panic_change
from app.db.base import Base
from app.models import Domain, DomainRecord, DomainRecordType, User, UserDomain
from app.schemas.panic import PanicChange


class PanicShutdownSchemaTests(TestCase):
    def test_accepts_shutdown_without_record_or_commit_fields(self) -> None:
        change = PanicChange(
            request_id="shutdown-request",
            domain="example.test",
            operation="DISABLE_DNS_INTENT",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        self.assertEqual(change.operation, "DISABLE_DNS_INTENT")

    def test_rejects_shutdown_with_a_record_field(self) -> None:
        with self.assertRaises(ValidationError):
            PanicChange(
                request_id="shutdown-request",
                domain="example.test",
                operation="DISABLE_DNS_INTENT",
                record_id=1,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )


class ApplyPanicShutdownTests(TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_deletes_protected_records_and_ie_policy_but_keeps_unprotected_records(self) -> None:
        with Session(self.engine) as session:
            types = {
                name: DomainRecordType(name=name) for name in ("A", "MX", "NS", "IE")
            }
            domain = Domain(name="example.test")
            user = User(
                first_name="Test",
                last_name="User",
                username="test.user",
                email="test@example.test",
                password_hash="unused",
            )
            membership = UserDomain(
                user=user,
                domain=domain,
                intent_public_key="a" * 44,
                panic_public_key="b" * 44,
            )
            domain.records.extend(
                [
                    DomainRecord(record_type=types["A"], value={"name": "@"}),
                    DomainRecord(record_type=types["MX"], value={"name": "@"}),
                    DomainRecord(record_type=types["NS"], value={"name": "@"}),
                    DomainRecord(
                        record_type=types["IE"],
                        value={"protected_operations": ["A", "MX"], "panic_quorum": 2},
                    ),
                ]
            )
            session.add_all([*types.values(), domain, user, membership])
            session.commit()

            apply_panic_change(
                domain,
                {"operation": "DISABLE_DNS_INTENT"},
                session,
            )
            session.commit()

            remaining_types = session.scalars(
                select(DomainRecordType.name)
                .join(DomainRecord)
                .where(DomainRecord.domain_id == domain.id)
            ).all()
            session.refresh(membership)

            self.assertEqual(remaining_types, ["NS"])
            self.assertIsNone(membership.intent_public_key)
            self.assertIsNone(membership.panic_public_key)

