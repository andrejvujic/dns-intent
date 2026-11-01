import base64
from datetime import datetime, timedelta, timezone
from unittest import TestCase

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes.domains import (
    apply_key_rotation,
    apply_panic_change,
    attach_panic_signature,
    finalize_member_removal,
    finalize_key_rotation,
)
from app.db.base import Base
from app.models import (
    Commit,
    CommitStatus,
    Domain,
    DomainRecord,
    DomainRecordType,
    MembershipStatus,
    PanicRequest,
    PanicRequestStatus,
    User,
    UserDomain,
)
from app.schemas.panic import PanicChange, PanicSignatureCreate, RotationKeysCreate


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

    def test_key_rotation_panic_does_not_contain_new_keys(self) -> None:
        change = PanicChange(
            request_id="rotation-request",
            domain="example.test",
            operation="ROTATE_KEYS",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        self.assertEqual(change.operation, "ROTATE_KEYS")

        with self.assertRaises(ValidationError):
            PanicChange(
                request_id="rotation-with-keys",
                domain="example.test",
                operation="ROTATE_KEYS",
                public_keys=[],
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )

    def test_member_removal_requires_only_a_target_user(self) -> None:
        change = PanicChange(
            request_id="remove-member-request",
            domain="example.test",
            operation="REMOVE_MEMBER",
            target_user_id=2,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        self.assertEqual(change.target_user_id, 2)

        with self.assertRaises(ValidationError):
            PanicChange(
                request_id="remove-without-target",
                domain="example.test",
                operation="REMOVE_MEMBER",
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

    def test_rotation_replaces_keys_and_clears_old_changes_without_deleting_records(self) -> None:
        with Session(self.engine) as session:
            types = {
                name: DomainRecordType(name=name) for name in ("A", "IE")
            }
            domain = Domain(name="rotate.test")
            user = User(
                first_name="Rotate",
                last_name="User",
                username="rotate.user",
                email="rotate@example.test",
                password_hash="unused",
            )
            membership = UserDomain(
                user=user,
                domain=domain,
                intent_public_key=base64.b64encode(b"o" * 32).decode(),
                panic_public_key=base64.b64encode(b"p" * 32).decode(),
            )
            other_user = User(
                first_name="Other",
                last_name="Voter",
                username="other.voter",
                email="other@example.test",
                password_hash="unused",
            )
            other_membership = UserDomain(
                user=other_user,
                domain=domain,
                intent_public_key=base64.b64encode(b"x" * 32).decode(),
                panic_public_key=base64.b64encode(b"y" * 32).decode(),
            )
            domain.records.extend(
                [
                    DomainRecord(record_type=types["A"], value={"name": "@"}),
                    DomainRecord(
                        record_type=types["IE"],
                        value={"protected_operations": ["A"], "panic_quorum": 1},
                    ),
                ]
            )
            session.add_all([
                *types.values(),
                domain,
                user,
                membership,
                other_user,
                other_membership,
            ])
            session.flush()
            now = datetime.now(timezone.utc)
            scheduled_commit = Commit(
                user_domain=membership,
                hash="r" * 44,
                signature="s" * 88,
                status=CommitStatus.READY,
                received_at=now,
                matures_at=now,
            )
            old_request = PanicRequest(
                request_id="old-rotation-panic",
                domain=domain,
                created_by=user,
                operation="DELETE_RECORD",
                change_json={"operation": "DELETE_RECORD", "record_id": 1},
                hash="q" * 44,
                creator_signature="s" * 88,
                required_quorum=1,
                expires_at=now + timedelta(hours=1),
                status=PanicRequestStatus.PENDING,
            )
            rotation_request = PanicRequest(
                request_id="rotation-panic",
                domain=domain,
                created_by=user,
                operation="ROTATE_KEYS",
                change_json={"operation": "ROTATE_KEYS"},
                hash="z" * 44,
                creator_signature="s" * 88,
                required_quorum=1,
                expires_at=now + timedelta(hours=1),
                status=PanicRequestStatus.QUORUM_REACHED,
            )
            session.add_all([scheduled_commit, old_request, rotation_request])
            session.commit()

            new_intent_key = base64.b64encode(b"i" * 32).decode()
            new_panic_key = base64.b64encode(b"k" * 32).decode()
            with self.assertRaises(HTTPException) as unauthorized:
                finalize_key_rotation(
                    other_user.id,
                    domain.id,
                    rotation_request.id,
                    RotationKeysCreate(
                        public_keys=[
                            {
                                "user_id": user.id,
                                "intent_public_key": new_intent_key,
                                "panic_public_key": new_panic_key,
                            }
                        ]
                    ),
                    session,
                )
            self.assertEqual(unauthorized.exception.status_code, 403)

            apply_key_rotation(
                domain,
                {user.id: (new_intent_key, new_panic_key)},
                session,
                preserve_panic_request_id=rotation_request.id,
            )
            session.commit()
            session.refresh(membership)

            remaining_types = set(
                session.scalars(
                    select(DomainRecordType.name)
                    .join(DomainRecord)
                    .where(DomainRecord.domain_id == domain.id)
                ).all()
            )
            self.assertEqual(remaining_types, {"A", "IE"})
            self.assertEqual(session.scalars(select(Commit)).all(), [])
            self.assertEqual(
                [item.id for item in session.scalars(select(PanicRequest)).all()],
                [rotation_request.id],
            )
            self.assertEqual(membership.intent_public_key, new_intent_key)
            self.assertEqual(membership.panic_public_key, new_panic_key)

    def test_initiator_removes_member_after_quorum_and_recalculates_policy(self) -> None:
        with Session(self.engine) as session:
            ie_type = DomainRecordType(name="IE")
            domain = Domain(name="remove.test")
            initiator = User(
                first_name="Action",
                last_name="Owner",
                username="action.owner",
                email="owner@remove.test",
                password_hash="unused",
            )
            target_user = User(
                first_name="Target",
                last_name="Member",
                username="target.member",
                email="target@remove.test",
                password_hash="unused",
            )
            third_user = User(
                first_name="Third",
                last_name="Member",
                username="third.member",
                email="third@remove.test",
                password_hash="unused",
            )
            initiator_membership = UserDomain(user=initiator, domain=domain)
            target_membership = UserDomain(
                user=target_user,
                domain=domain,
                intent_public_key="i" * 44,
                panic_public_key="p" * 44,
            )
            third_membership = UserDomain(user=third_user, domain=domain)
            domain.records.append(
                DomainRecord(
                    record_type=ie_type,
                    value={"protected_operations": ["A"], "panic_quorum": 3},
                )
            )
            session.add_all([
                ie_type,
                domain,
                initiator,
                target_user,
                third_user,
                initiator_membership,
                target_membership,
                third_membership,
            ])
            session.flush()
            request = PanicRequest(
                request_id="approved-removal",
                domain=domain,
                created_by=initiator,
                operation="REMOVE_MEMBER",
                change_json={"operation": "REMOVE_MEMBER", "target_user_id": target_user.id},
                hash="h" * 44,
                creator_signature="s" * 88,
                required_quorum=2,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                status=PanicRequestStatus.QUORUM_REACHED,
            )
            session.add(request)
            session.commit()

            with self.assertRaises(HTTPException) as unauthorized:
                finalize_member_removal(
                    third_user.id,
                    domain.id,
                    request.id,
                    session,
                )
            self.assertEqual(unauthorized.exception.status_code, 403)

            response = finalize_member_removal(
                initiator.id,
                domain.id,
                request.id,
                session,
            )

            session.refresh(target_membership)
            ie_record = session.scalar(
                select(DomainRecord).where(DomainRecord.domain_id == domain.id)
            )
            self.assertEqual(response.status, PanicRequestStatus.APPLIED.value)
            self.assertFalse(target_membership.is_active)
            self.assertEqual(target_membership.membership_status, MembershipStatus.DECLINED)
            self.assertIsNone(target_membership.intent_public_key)
            self.assertIsNone(target_membership.panic_public_key)
            self.assertEqual(ie_record.value["panic_quorum"], 2)

    def test_removal_target_cannot_attach_a_panic_signature(self) -> None:
        with Session(self.engine) as session:
            domain = Domain(name="blocked-vote.test")
            initiator = User(
                first_name="Action", last_name="Owner", username="owner",
                email="owner@blocked.test", password_hash="unused",
            )
            target_user = User(
                first_name="Target", last_name="Member", username="target",
                email="target@blocked.test", password_hash="unused",
            )
            session.add_all([
                domain,
                initiator,
                target_user,
                UserDomain(user=initiator, domain=domain, panic_public_key="a" * 44),
                UserDomain(user=target_user, domain=domain, panic_public_key="b" * 44),
            ])
            session.flush()
            request = PanicRequest(
                request_id="blocked-removal-vote",
                domain=domain,
                created_by=initiator,
                operation="REMOVE_MEMBER",
                change_json={"operation": "REMOVE_MEMBER", "target_user_id": target_user.id},
                hash="h" * 44,
                creator_signature="s" * 88,
                required_quorum=1,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                status=PanicRequestStatus.PENDING,
            )
            session.add(request)
            session.commit()

            with self.assertRaises(HTTPException) as blocked:
                attach_panic_signature(
                    target_user.id,
                    domain.id,
                    request.id,
                    PanicSignatureCreate(signature="s" * 88),
                    session,
                )
            self.assertEqual(blocked.exception.status_code, 403)
