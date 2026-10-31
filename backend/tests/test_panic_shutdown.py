from datetime import datetime, timedelta, timezone
from unittest import TestCase

from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes.domains import apply_panic_change
from app.db.base import Base
from app.models import (
    Commit,
    CommitStatus,
    Domain,
    DomainRecord,
    DomainRecordType,
    PanicRequest,
    PanicRequestStatus,
    User,
    UserDomain,
)
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

    def test_keeps_dns_records_but_deletes_policy_commits_and_old_panic_requests(self) -> None:
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
            session.flush()
            now = datetime.now(timezone.utc)
            scheduled_commit = Commit(
                user_domain=membership,
                hash="c" * 44,
                signature="s" * 88,
                status=CommitStatus.HOLDING,
                received_at=now,
                matures_at=now + timedelta(hours=1),
            )
            old_panic_request = PanicRequest(
                request_id="old-panic-request",
                domain=domain,
                created_by=user,
                operation="DELETE_RECORD",
                change_json={"operation": "DELETE_RECORD", "record_id": 1},
                hash="p" * 44,
                creator_signature="s" * 88,
                required_quorum=2,
                expires_at=now + timedelta(hours=1),
                status=PanicRequestStatus.PENDING,
            )
            shutdown_request = PanicRequest(
                request_id="shutdown-request",
                domain=domain,
                created_by=user,
                operation="DISABLE_DNS_INTENT",
                change_json={"operation": "DISABLE_DNS_INTENT"},
                hash="d" * 44,
                creator_signature="s" * 88,
                required_quorum=2,
                expires_at=now + timedelta(hours=1),
                status=PanicRequestStatus.QUORUM_REACHED,
            )
            session.add_all([scheduled_commit, old_panic_request, shutdown_request])
            session.commit()

            apply_panic_change(
                domain,
                {"operation": "DISABLE_DNS_INTENT"},
                session,
                preserve_panic_request_id=shutdown_request.id,
            )
            session.commit()

            remaining_types = session.scalars(
                select(DomainRecordType.name)
                .join(DomainRecord)
                .where(DomainRecord.domain_id == domain.id)
            ).all()
            session.refresh(membership)

            self.assertEqual(set(remaining_types), {"A", "MX", "NS"})
            self.assertEqual(session.scalars(select(Commit)).all(), [])
            remaining_panic_requests = session.scalars(select(PanicRequest)).all()
            self.assertEqual([item.id for item in remaining_panic_requests], [shutdown_request.id])
            self.assertIsNone(membership.intent_public_key)
            self.assertIsNone(membership.panic_public_key)
