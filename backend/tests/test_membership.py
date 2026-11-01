from unittest import TestCase

from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes.auth import register
from app.api.routes.domains import (
    create_domain_record,
    get_domain_team,
    list_domain_members,
    vote_on_membership_request,
)
from app.db.base import Base
from app.models import (
    Domain,
    DomainRecord,
    DomainRecordType,
    MembershipStatus,
    User,
    UserDomain,
)
from app.schemas import DomainRecordCreate, MembershipVoteCreate, RegisterRequest


STRONG_PASSWORD = "Sigurna#Lozinka7"


class RegisterRequestTests(TestCase):
    def base(self, **overrides) -> dict:
        data = {
            "first_name": "Nova",
            "last_name": "Osoba",
            "email": "nova@demo.test",
            "password": STRONG_PASSWORD,
            "domain_id": 1,
        }
        data.update(overrides)
        return data

    def test_accepts_strong_password(self) -> None:
        self.assertEqual(RegisterRequest(**self.base()).email, "nova@demo.test")

    def test_rejects_weak_passwords(self) -> None:
        for weak in ("short1!A", "nouppercase1!", "NOLOWERCASE1!", "NoNumbers!!xx", "NoSpecial123x"):
            with self.assertRaises(ValidationError, msg=weak):
                RegisterRequest(**self.base(password=weak))

    def test_requires_names_and_rejects_recovery_email(self) -> None:
        with self.assertRaises(ValidationError):
            RegisterRequest(**self.base(first_name="   "))
        with self.assertRaises(ValidationError):
            RegisterRequest(**self.base(last_name=""))
        with self.assertRaises(ValidationError):
            RegisterRequest(**self.base(recovery_email="rezerva@demo.test"))

    def test_rejects_invalid_email(self) -> None:
        with self.assertRaises(ValidationError):
            RegisterRequest(**self.base(email="not-an-email"))


class MembershipFlowTests(TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.types = {name: DomainRecordType(name=name) for name in ("A", "NS", "IE")}
        self.session.add_all(self.types.values())
        self.domain = Domain(name="dnsintent.test")
        self.members = []
        for index in range(5):
            user = User(
                first_name=f"User{index}",
                last_name="Seed",
                username=f"user{index}",
                email=f"user{index}@dnsintent.test",
                password_hash="x",
            )
            self.domain.user_memberships.append(UserDomain(user=user))
            self.members.append(user)
        self.session.add(self.domain)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def register_applicant(self) -> User:
        response = register(
            RegisterRequest(
                first_name="Nova",
                last_name="Osoba",
                email="nova@demo.test",
                password=STRONG_PASSWORD,
                domain_id=self.domain.id,
            ),
            BackgroundTasks(),
            self.session,
        )
        return self.session.get(User, response.user.id)

    def vote(self, voter: User, decision: str):
        team = get_domain_team(voter.id, self.domain.id, self.session)
        membership_id = team.requests[0].membership_id
        return vote_on_membership_request(
            voter.id,
            self.domain.id,
            membership_id,
            MembershipVoteCreate(decision=decision),
            self.session,
        )

    def test_new_user_starts_pending_and_is_not_a_key_holder(self) -> None:
        applicant = self.register_applicant()
        team = get_domain_team(applicant.id, self.domain.id, self.session)
        self.assertEqual(team.my_status, "PENDING")
        self.assertEqual(team.required_quorum, 3)
        member_ids = {m.id for m in list_domain_members(self.members[0].id, self.domain.id, self.session)}
        self.assertNotIn(applicant.id, member_ids)

    def test_majority_accepts(self) -> None:
        applicant = self.register_applicant()
        self.vote(self.members[0], "ACCEPT")
        self.vote(self.members[1], "ACCEPT")
        team = self.vote(self.members[2], "ACCEPT")
        self.assertEqual(team.requests, [])
        status = self.session.scalar(
            select(UserDomain.membership_status).where(UserDomain.user_id == applicant.id)
        )
        self.assertEqual(status, MembershipStatus.ACCEPTED)

    def test_majority_declines_and_two_votes_are_not_enough(self) -> None:
        applicant = self.register_applicant()
        self.vote(self.members[0], "REJECT")
        team = self.vote(self.members[1], "REJECT")
        self.assertEqual(team.requests[0].against_count, 2)
        self.vote(self.members[2], "REJECT")
        status = self.session.scalar(
            select(UserDomain.membership_status).where(UserDomain.user_id == applicant.id)
        )
        self.assertEqual(status, MembershipStatus.DECLINED)

    def test_member_cannot_vote_twice_and_applicant_cannot_vote(self) -> None:
        applicant = self.register_applicant()
        self.vote(self.members[0], "ACCEPT")
        with self.assertRaises(HTTPException):
            self.vote(self.members[0], "ACCEPT")
        with self.assertRaises(HTTPException):
            self.vote(applicant, "ACCEPT")

    def test_pending_user_edits_only_unprotected_domain(self) -> None:
        applicant = self.register_applicant()
        payload = DomainRecordCreate(type="A", value={"name": "new", "address": "192.0.2.50", "ttl": 3600})
        create_domain_record(applicant.id, self.domain.id, payload, self.session)

        self.session.add(DomainRecord(domain=self.domain, record_type=self.types["IE"], value={
            "name": "@", "ttl": 3600, "panic_quorum": 3, "delay_seconds": 1800,
            "protected_operations": ["NS"],
        }))
        self.session.commit()
        payload = DomainRecordCreate(type="A", value={"name": "other", "address": "192.0.2.51", "ttl": 3600})
        with self.assertRaises(HTTPException) as raised:
            create_domain_record(applicant.id, self.domain.id, payload, self.session)
        self.assertEqual(raised.exception.status_code, 403)

    def test_duplicate_email_is_rejected(self) -> None:
        self.register_applicant()
        with self.assertRaises(HTTPException):
            self.register_applicant()
