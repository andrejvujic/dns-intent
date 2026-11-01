import base64
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes.auth import register
from app.api.routes.domains import (
    create_domain,
    create_domain_record,
    delete_domain_record,
    enable_dns_intent,
    get_domain_team,
    invite_to_domain,
    list_domain_members,
    list_invite_candidates,
    list_user_domains,
    update_domain_record,
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
from app.schemas import (
    DomainCreate,
    DomainRecordCreate,
    DomainRecordUpdate,
    InvitationCreate,
    MembershipVoteCreate,
    RegisterRequest,
)
from app.schemas.domain_record import IntentEnforcementCreate


STRONG_PASSWORD = "Sigurna#Lozinka7"


class RegisterRequestTests(TestCase):
    def base(self, **overrides) -> dict:
        data = {
            "first_name": "Nova",
            "last_name": "Osoba",
            "email": "nova@demo.test",
            "password": STRONG_PASSWORD,
        }
        data.update(overrides)
        return data

    def test_accepts_strong_password(self) -> None:
        self.assertEqual(RegisterRequest(**self.base()).email, "nova@demo.test")

    def test_rejects_weak_passwords(self) -> None:
        for weak in ("short1!A", "nouppercase1!", "NOLOWERCASE1!", "NoNumbers!!xx", "NoSpecial123x"):
            with self.assertRaises(ValidationError, msg=weak):
                RegisterRequest(**self.base(password=weak))

    def test_requires_names_and_rejects_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            RegisterRequest(**self.base(first_name="   "))
        with self.assertRaises(ValidationError):
            RegisterRequest(**self.base(last_name=""))
        # The domain is no longer chosen at registration.
        with self.assertRaises(ValidationError):
            RegisterRequest(**self.base(domain_id=1))
        with self.assertRaises(ValidationError):
            RegisterRequest(**self.base(recovery_email="rezerva@demo.test"))

    def test_rejects_invalid_email(self) -> None:
        with self.assertRaises(ValidationError):
            RegisterRequest(**self.base(email="not-an-email"))


class DomainCreateTests(TestCase):
    def test_normalizes_and_validates_domain_names(self) -> None:
        self.assertEqual(DomainCreate(name=" Example.COM. ").name, "example.com")
        for bad in ("localhost", "bad_domain.com", "-start.com", "a..b.com"):
            with self.assertRaises(ValidationError, msg=bad):
                DomainCreate(name=bad)


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

    def register_user(self, email: str = "pera@demo.test") -> User:
        response = register(
            RegisterRequest(
                first_name="Pera",
                last_name="Peric",
                email=email,
                password=STRONG_PASSWORD,
            ),
            self.session,
        )
        return self.session.get(User, response.user.id)

    def invite(self, invitee: User, inviter: User | None = None):
        inviter = inviter or self.members[0]
        return invite_to_domain(
            inviter.id,
            self.domain.id,
            InvitationCreate(user_id=invitee.id),
            BackgroundTasks(),
            self.session,
        )

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

    def status_of(self, user: User) -> MembershipStatus | None:
        return self.session.scalar(
            select(UserDomain.membership_status).where(
                UserDomain.user_id == user.id,
                UserDomain.domain_id == self.domain.id,
            )
        )

    def test_registration_gives_no_domain(self) -> None:
        pera = self.register_user()
        self.assertEqual(list_user_domains(pera.id, self.session), [])
        self.assertIsNone(self.status_of(pera))

    def intent_payload(self, quorum: int) -> IntentEnforcementCreate:
        public_key = base64.b64encode(
            Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        ).decode()
        return IntentEnforcementCreate(
            panic_quorum=quorum,
            delay_seconds=30,
            protected_operations=["NS"],
            public_keys=[
                {"user_id": user.id, "intent_public_key": public_key, "panic_public_key": public_key}
                for user in self.members
            ],
        )

    def test_intent_accepts_quorum_one_below_member_count(self) -> None:
        record = enable_dns_intent(
            self.members[0].id, self.domain.id, self.intent_payload(4), self.session,
        )
        self.assertEqual(record.value["panic_quorum"], 4)

    def test_intent_rejects_quorum_at_or_above_member_count(self) -> None:
        for quorum in (5, 6, 100):
            with self.subTest(quorum=quorum), self.assertRaises(HTTPException) as raised:
                enable_dns_intent(
                    self.members[0].id, self.domain.id, self.intent_payload(quorum), self.session,
                )
            self.assertEqual(raised.exception.status_code, 422)
            self.assertIn("at most 4", raised.exception.detail)

    def test_intent_quorum_counts_only_active_accepted_members(self) -> None:
        self.domain.user_memberships[3].membership_status = MembershipStatus.PENDING
        self.domain.user_memberships[4].is_active = False
        self.session.commit()
        with self.assertRaises(HTTPException) as raised:
            enable_dns_intent(
                self.members[0].id, self.domain.id, self.intent_payload(3), self.session,
            )
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("at most 2 for 3", raised.exception.detail)

    def test_intent_requires_at_least_two_members(self) -> None:
        for membership in self.domain.user_memberships[1:]:
            membership.is_active = False
        self.session.commit()
        with self.assertRaises(HTTPException) as raised:
            enable_dns_intent(
                self.members[0].id, self.domain.id, self.intent_payload(1), self.session,
            )
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("At least two", raised.exception.detail)

    def test_new_user_is_listed_as_candidate_until_invited(self) -> None:
        pera = self.register_user()
        candidates = list_invite_candidates(self.members[0].id, self.domain.id, self.session)
        self.assertEqual([c.email for c in candidates], ["pera@demo.test"])

        self.invite(pera)
        candidates = list_invite_candidates(self.members[0].id, self.domain.id, self.session)
        self.assertEqual(candidates, [])

    def test_invitation_starts_a_vote_with_the_inviters_accept(self) -> None:
        pera = self.register_user()
        team = self.invite(pera)
        self.assertEqual(self.status_of(pera), MembershipStatus.PENDING)
        self.assertEqual(team.required_quorum, 3)
        self.assertEqual(team.requests[0].for_count, 1)
        self.assertEqual(team.requests[0].invited_by, "User0 Seed")
        self.assertEqual(team.requests[0].user_vote, "ACCEPT")
        member_ids = {m.id for m in list_domain_members(self.members[0].id, self.domain.id, self.session)}
        self.assertNotIn(pera.id, member_ids)

    def test_majority_accepts(self) -> None:
        pera = self.register_user()
        self.invite(pera)
        self.vote(self.members[1], "ACCEPT")
        team = self.vote(self.members[2], "ACCEPT")
        self.assertEqual(team.requests, [])
        self.assertEqual(self.status_of(pera), MembershipStatus.ACCEPTED)

    def test_majority_declines_and_user_can_be_proposed_again(self) -> None:
        pera = self.register_user()
        self.invite(pera)
        self.vote(self.members[1], "REJECT")
        team = self.vote(self.members[2], "REJECT")
        self.assertEqual(team.requests[0].against_count, 2)
        self.vote(self.members[3], "REJECT")
        self.assertEqual(self.status_of(pera), MembershipStatus.DECLINED)

        team = self.invite(pera, inviter=self.members[4])
        self.assertEqual(self.status_of(pera), MembershipStatus.PENDING)
        self.assertEqual((team.requests[0].for_count, team.requests[0].against_count), (1, 0))

    def test_votes_are_single_and_pending_users_have_no_say(self) -> None:
        pera = self.register_user()
        mika = self.register_user("mika@demo.test")
        self.invite(pera)
        with self.assertRaises(HTTPException):
            self.vote(self.members[0], "ACCEPT")  # the inviter already voted
        with self.assertRaises(HTTPException):
            self.vote(pera, "ACCEPT")
        with self.assertRaises(HTTPException):
            self.invite(mika, inviter=pera)
        with self.assertRaises(HTTPException):
            self.invite(pera)  # already pending

    def test_pending_user_edits_only_unprotected_domain(self) -> None:
        pera = self.register_user()
        self.invite(pera)
        payload = DomainRecordCreate(type="A", value={"name": "new", "address": "192.0.2.50", "ttl": 3600})
        create_domain_record(pera.id, self.domain.id, payload, self.session)

        self.session.add(DomainRecord(domain=self.domain, record_type=self.types["IE"], value={
            "name": "@", "ttl": 3600, "panic_quorum": 3, "delay_seconds": 1800,
            "protected_operations": ["NS"],
        }))
        self.session.commit()
        payload = DomainRecordCreate(type="A", value={"name": "other", "address": "192.0.2.51", "ttl": 3600})
        with self.assertRaises(HTTPException) as raised:
            create_domain_record(pera.id, self.domain.id, payload, self.session)
        self.assertEqual(raised.exception.status_code, 403)

    def test_pending_user_cannot_update_or_delete_on_protected_domain(self) -> None:
        pera = self.register_user()
        self.invite(pera)
        record = DomainRecord(domain=self.domain, record_type=self.types["A"], value={
            "name": "www", "address": "192.0.2.20", "ttl": 3600,
        })
        self.session.add(record)
        self.session.add(DomainRecord(domain=self.domain, record_type=self.types["IE"], value={
            "name": "@", "ttl": 3600, "panic_quorum": 3, "delay_seconds": 1800,
            "protected_operations": ["NS"],
        }))
        self.session.commit()

        with self.assertRaises(HTTPException) as updated:
            update_domain_record(
                pera.id, self.domain.id, record.id,
                DomainRecordUpdate(value={"name": "www", "address": "192.0.2.99", "ttl": 3600}),
                self.session,
            )
        self.assertEqual(updated.exception.status_code, 403)

        with self.assertRaises(HTTPException) as deleted:
            delete_domain_record(pera.id, self.domain.id, record.id, self.session)
        self.assertEqual(deleted.exception.status_code, 403)
        self.session.refresh(record)
        self.assertEqual(record.value["address"], "192.0.2.20")

    def test_any_user_can_create_a_domain_and_owns_it(self) -> None:
        pera = self.register_user()
        summary = create_domain(pera.id, DomainCreate(name="pera.test"), self.session)
        self.assertEqual(summary.membership_status, "ACCEPTED")
        team = get_domain_team(pera.id, summary.id, self.session)
        self.assertEqual((team.accepted_count, team.required_quorum), (1, 1))

        with self.assertRaises(HTTPException) as duplicate:
            create_domain(self.members[0].id, DomainCreate(name="PERA.test"), self.session)
        self.assertEqual(duplicate.exception.status_code, 409)

    def test_duplicate_email_is_rejected(self) -> None:
        self.register_user()
        with self.assertRaises(HTTPException):
            self.register_user()
