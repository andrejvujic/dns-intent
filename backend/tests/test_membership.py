import base64
from datetime import datetime, timedelta, timezone
from unittest import TestCase
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes.auth import register
from app.api.routes.domains import (
    apply_membership_request,
    attach_panic_signature,
    apply_key_rotation,
    create_domain,
    create_panic_change,
    create_domain_record,
    delete_domain_record,
    enable_dns_intent,
    get_domain_team,
    finalize_member_addition,
    load_panic_request,
    invite_to_domain,
    list_domain_members,
    list_invite_candidates,
    list_user_domains,
    update_domain_record,
    vote_on_membership_request,
    vote_on_panic_change,
)
from app.db.base import Base
from app.models import (
    Domain,
    DomainRecord,
    DomainRecordType,
    MembershipStatus,
    MembershipVote,
    PanicRequest,
    PanicSignature,
    User,
    UserDomain,
)
from app.schemas import (
    DomainCreate,
    DomainRecordCreate,
    DomainRecordUpdate,
    InvitationCreate,
    MemberPublicKeys,
    MembershipVoteCreate,
    RegisterRequest,
)
from app.schemas.domain_record import IntentEnforcementCreate
from app.schemas.panic import PanicChange, PanicCreate, PanicSignatureCreate, PanicVoteCreate
from scripts.create_panic_signature import create_panic_bundle


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
        self.panic_keys = {}
        self.protected = False

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
        if self.protected:
            change = self.invitation_change(invitee)
            bundle = create_panic_bundle(change, self.panic_keys.get(inviter.id, Ed25519PrivateKey.generate()))
            self.last_panic = create_panic_change(
                inviter.id, self.domain.id,
                PanicCreate(change=change, **bundle["panic_request"]),
                BackgroundTasks(), self.session,
            )
            return get_domain_team(inviter.id, self.domain.id, self.session)
        return invite_to_domain(
            inviter.id,
            self.domain.id,
            InvitationCreate(user_id=invitee.id),
            BackgroundTasks(),
            self.session,
        )

    def invitation_change(self, invitee: User, **overrides) -> PanicChange:
        data = dict(
            request_id=str(uuid4()), domain=self.domain.name, operation="ADD_MEMBER",
            member_user_id=invitee.id, member_email=invitee.email,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        data.update(overrides)
        return PanicChange(**data)

    def member_keys(self, user: User) -> MemberPublicKeys:
        public_key = base64.b64encode(
            Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        ).decode()
        return MemberPublicKeys(
            user_id=user.id,
            intent_public_key=public_key,
            panic_public_key=public_key,
        )

    def protect_domain(self, quorum: int = 3) -> None:
        self.protected = True
        for member in self.members:
            private_key = Ed25519PrivateKey.generate()
            self.panic_keys[member.id] = private_key
            membership = self.session.scalar(select(UserDomain).where(
                UserDomain.user_id == member.id, UserDomain.domain_id == self.domain.id,
            ))
            membership.panic_public_key = base64.b64encode(private_key.public_key().public_bytes_raw()).decode()
        self.session.add(DomainRecord(domain=self.domain, record_type=self.types["IE"], value={
            "name": "@", "ttl": 3600, "panic_quorum": quorum, "delay_seconds": 1800,
            "protected_operations": ["NS"],
        }))
        self.session.commit()

    def vote(self, voter: User, decision: str):
        team = get_domain_team(voter.id, self.domain.id, self.session)
        panic_id = team.requests[0].panic_request_id
        signature = self.signature_for(voter, panic_id)
        attach_panic_signature(voter.id, self.domain.id, panic_id, PanicSignatureCreate(signature=signature), self.session)
        vote_on_panic_change(
            voter.id, self.domain.id, panic_id,
            PanicVoteCreate(decision=decision, signature=signature), self.session,
        )
        return get_domain_team(voter.id, self.domain.id, self.session)

    def signature_for(self, voter: User, panic_id: int) -> str:
        panic = self.session.get(PanicRequest, panic_id)
        key = self.panic_keys.get(voter.id, Ed25519PrivateKey.generate())
        return create_panic_bundle(PanicChange(**panic.change_json), key)["signature"]

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
        self.assertEqual(list_invite_candidates(self.members[0].id, self.domain.id, self.session, ""), [])
        candidates = list_invite_candidates(self.members[0].id, self.domain.id, self.session, "PERA@")
        self.assertEqual([c.email for c in candidates], ["pera@demo.test"])

        self.invite(pera)
        candidates = list_invite_candidates(self.members[0].id, self.domain.id, self.session, "pera@")
        self.assertEqual(candidates, [])

    def test_unprotected_invitation_adds_immediately(self) -> None:
        pera = self.register_user()
        team = self.invite(pera)
        self.assertEqual(self.status_of(pera), MembershipStatus.ACCEPTED)
        self.assertEqual(team.requests, [])

    def test_unsigned_invitation_and_legacy_vote_or_apply_cannot_bypass_panic(self) -> None:
        self.protect_domain()
        pera = self.register_user()
        with self.assertRaises(HTTPException) as unsigned:
            invite_to_domain(self.members[0].id, self.domain.id, InvitationCreate(user_id=pera.id), BackgroundTasks(), self.session)
        self.assertEqual(unsigned.exception.status_code, 409)
        self.assertIsNone(self.status_of(pera))
        team = self.invite(pera)
        membership_id = team.requests[0].membership_id
        with self.assertRaises(HTTPException) as vote:
            vote_on_membership_request(self.members[1].id, self.domain.id, membership_id, MembershipVoteCreate(decision="ACCEPT"), self.session)
        self.assertEqual(vote.exception.status_code, 409)
        self.vote(self.members[1], "ACCEPT")
        self.vote(self.members[2], "ACCEPT")
        with self.assertRaises(HTTPException) as apply:
            apply_membership_request(self.members[0].id, self.domain.id, membership_id, self.session)
        self.assertEqual(apply.exception.status_code, 409)
        self.assertEqual(self.status_of(pera), MembershipStatus.QUORUM_REACHED)

    def test_invitation_requires_panic_key_and_signature_bound_to_exact_change(self) -> None:
        self.protect_domain()
        pera = self.register_user()
        change = self.invitation_change(pera)
        with self.assertRaises(ValidationError):
            PanicCreate(change=change)
        intent_key = Ed25519PrivateKey.generate()
        membership = self.session.scalar(select(UserDomain).where(UserDomain.user_id == self.members[0].id))
        membership.intent_public_key = base64.b64encode(intent_key.public_key().public_bytes_raw()).decode()
        self.session.commit()
        for key, signed_change, submitted_change in (
            (intent_key, change, change),
            (self.panic_keys[self.members[1].id], change, change),
            (self.panic_keys[self.members[0].id], change, self.invitation_change(pera)),
        ):
            signature = create_panic_bundle(signed_change, key)["signature"]
            with self.assertRaises(HTTPException) as invalid:
                create_panic_change(self.members[0].id, self.domain.id, PanicCreate(change=submitted_change, signature=signature), BackgroundTasks(), self.session)
            self.assertEqual(invalid.exception.status_code, 403)
        self.assertIsNone(self.status_of(pera))
        self.assertEqual(list(self.session.scalars(select(PanicRequest))), [])

    def test_signed_candidate_identity_and_operation_fields_are_checked(self) -> None:
        self.protect_domain()
        pera = self.register_user()
        change = self.invitation_change(pera, member_email="someone-else@demo.test")
        bundle = create_panic_bundle(change, self.panic_keys[self.members[0].id])
        with self.assertRaises(HTTPException) as mismatch:
            create_panic_change(self.members[0].id, self.domain.id, PanicCreate(change=change, **bundle["panic_request"]), BackgroundTasks(), self.session)
        self.assertEqual(mismatch.exception.status_code, 400)
        for fields in ({"member_user_id": None}, {"member_email": None}, {"record_id": 1}, {"value": {}}, {"operation": "ROTATE_KEYS"}):
            with self.assertRaises(ValidationError):
                self.invitation_change(pera, **fields)

    def test_vote_requires_attached_signature_for_this_member_and_request(self) -> None:
        self.protect_domain()
        pera = self.register_user()
        self.invite(pera)
        panic_id = self.last_panic.id
        voter = self.members[1]
        signature = self.signature_for(voter, panic_id)
        with self.assertRaises(ValidationError):
            PanicVoteCreate(decision="ACCEPT")
        with self.assertRaises(HTTPException) as unattached:
            vote_on_panic_change(voter.id, self.domain.id, panic_id, PanicVoteCreate(decision="ACCEPT", signature=signature), self.session)
        self.assertEqual(unattached.exception.status_code, 403)
        another_change = self.invitation_change(pera)
        wrong_signatures = [
            self.signature_for(self.members[0], panic_id),
            create_panic_bundle(another_change, self.panic_keys[voter.id])["signature"],
        ]
        for wrong in wrong_signatures:
            with self.assertRaises(HTTPException) as invalid:
                attach_panic_signature(voter.id, self.domain.id, panic_id, PanicSignatureCreate(signature=wrong), self.session)
            self.assertEqual(invalid.exception.status_code, 403)
        self.assertEqual(get_domain_team(voter.id, self.domain.id, self.session).requests[0].for_count, 1)
        team = self.vote(voter, "REJECT")
        self.assertEqual(team.requests[0].against_count, 1)
        stored = list(self.session.scalars(select(PanicSignature).where(PanicSignature.panic_request_id == panic_id)))
        self.assertEqual(len(stored), 2)
        self.assertTrue(all(vote.is_valid and vote.signature for vote in stored))
        with self.assertRaises(HTTPException):
            self.vote(voter, "ACCEPT")

    def test_uses_configured_panic_quorum_and_requires_explicit_application(self) -> None:
        self.protect_domain(quorum=2)
        pera = self.register_user()
        self.invite(pera)
        with self.assertRaises(HTTPException) as early:
            finalize_member_addition(self.members[0].id, self.domain.id, self.last_panic.id, self.member_keys(pera), self.session)
        self.assertEqual(early.exception.status_code, 409)
        team = self.vote(self.members[1], "ACCEPT")
        self.assertEqual(team.requests[0].required_quorum, 2)
        self.assertEqual(team.requests[0].status, "QUORUM_REACHED")
        self.assertNotIn(pera.id, [m.id for m in list_domain_members(self.members[0].id, self.domain.id, self.session)])
        finalize_member_addition(self.members[0].id, self.domain.id, self.last_panic.id, self.member_keys(pera), self.session)
        self.assertEqual(self.status_of(pera), MembershipStatus.ACCEPTED)

    def test_expired_invitation_can_restart_but_old_signature_cannot_be_replayed(self) -> None:
        self.protect_domain()
        pera = self.register_user()
        self.invite(pera)
        old_id = self.last_panic.id
        signature = self.signature_for(self.members[1], old_id)
        request = self.session.get(PanicRequest, old_id)
        request.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.session.commit()
        self.assertEqual(load_panic_request(old_id, self.domain.id, self.session).status, "EXPIRED")
        self.assertEqual(self.status_of(pera), MembershipStatus.DECLINED)
        self.invite(pera)
        with self.assertRaises(HTTPException) as replay:
            attach_panic_signature(self.members[1].id, self.domain.id, self.last_panic.id, PanicSignatureCreate(signature=signature), self.session)
        self.assertEqual(replay.exception.status_code, 403)

    def test_key_rotation_cancels_pending_member_addition(self) -> None:
        self.protect_domain(quorum=1)
        pera = self.register_user()
        self.invite(pera)
        old_id = self.last_panic.id
        apply_key_rotation(self.domain, {}, self.session, preserve_panic_request_id=-1)
        self.session.commit()
        self.assertEqual(self.status_of(pera), MembershipStatus.DECLINED)
        with self.assertRaises(HTTPException) as deleted:
            finalize_member_addition(self.members[0].id, self.domain.id, old_id, self.member_keys(pera), self.session)
        self.assertEqual(deleted.exception.status_code, 404)

    def test_legacy_unsigned_votes_do_not_count_and_can_restart_signed(self) -> None:
        self.protect_domain()
        pera = self.register_user()
        applicant = UserDomain(user=pera, domain=self.domain, membership_status=MembershipStatus.QUORUM_REACHED)
        self.session.add(applicant)
        voter_ids = list(self.session.scalars(select(UserDomain.id).where(UserDomain.membership_status == MembershipStatus.ACCEPTED)))
        applicant.membership_votes.extend(MembershipVote(voter_user_domain_id=voter_id, decision="ACCEPT") for voter_id in voter_ids)
        self.session.commit()
        legacy = get_domain_team(self.members[0].id, self.domain.id, self.session).requests[0]
        self.assertEqual((legacy.status, legacy.for_count, legacy.can_finalize), ("SIGNATURE_REQUIRED", 0, False))
        self.assertIsNone(legacy.panic_request_id)
        restarted = self.invite(pera).requests[0]
        self.assertEqual((restarted.status, restarted.for_count), ("PENDING", 1))
        self.assertIsNotNone(restarted.panic_request_id)

    def test_invitation_starts_a_vote_with_the_inviters_accept(self) -> None:
        self.protect_domain()
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
        self.protect_domain()
        pera = self.register_user()
        self.invite(pera)
        self.vote(self.members[1], "ACCEPT")
        team = self.vote(self.members[2], "ACCEPT")
        self.assertEqual(team.requests[0].status, "QUORUM_REACHED")
        self.assertEqual(self.status_of(pera), MembershipStatus.QUORUM_REACHED)
        self.assertEqual(list_user_domains(pera.id, self.session), [])
        self.assertFalse(team.requests[0].can_finalize)
        inviter_team = get_domain_team(self.members[0].id, self.domain.id, self.session)
        self.assertTrue(inviter_team.requests[0].can_finalize)
        with self.assertRaises(HTTPException) as unauthorized:
            finalize_member_addition(self.members[1].id, self.domain.id, team.requests[0].panic_request_id, self.member_keys(pera), self.session)
        self.assertEqual(unauthorized.exception.status_code, 403)
        applied = finalize_member_addition(self.members[0].id, self.domain.id, team.requests[0].panic_request_id, self.member_keys(pera), self.session)
        self.assertEqual(applied.status, "APPLIED")
        self.assertEqual(get_domain_team(self.members[0].id, self.domain.id, self.session).requests, [])
        self.assertEqual(self.status_of(pera), MembershipStatus.ACCEPTED)
        with self.assertRaises(HTTPException) as replay:
            finalize_member_addition(self.members[0].id, self.domain.id, team.requests[0].panic_request_id, self.member_keys(pera), self.session)
        self.assertEqual(replay.exception.status_code, 409)

    def test_one_member_quorum_still_requires_inviter_application(self) -> None:
        for member in self.members[1:]:
            membership = self.session.scalar(select(UserDomain).where(
                UserDomain.domain_id == self.domain.id, UserDomain.user_id == member.id,
            ))
            membership.is_active = False
        self.session.commit()
        self.protect_domain(quorum=1)
        pera = self.register_user()
        team = self.invite(pera)
        self.assertEqual(team.requests[0].status, "QUORUM_REACHED")
        self.assertEqual(self.status_of(pera), MembershipStatus.QUORUM_REACHED)
        finalize_member_addition(self.members[0].id, self.domain.id, team.requests[0].panic_request_id, self.member_keys(pera), self.session)
        self.assertEqual(self.status_of(pera), MembershipStatus.ACCEPTED)

    def test_majority_declines_and_user_can_be_proposed_again(self) -> None:
        self.protect_domain()
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
        self.protect_domain()
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
        self.protect_domain()
        pera = self.register_user()
        self.invite(pera)
        payload = DomainRecordCreate(type="A", value={"name": "new", "address": "192.0.2.50", "ttl": 3600})
        with self.assertRaises(HTTPException):
            create_domain_record(pera.id, self.domain.id, payload, self.session)
        self.session.delete(self.session.scalar(select(DomainRecord).where(DomainRecord.domain_id == self.domain.id)))
        self.session.commit()
        create_domain_record(pera.id, self.domain.id, payload, self.session)

    def test_pending_user_cannot_update_or_delete_on_protected_domain(self) -> None:
        self.protect_domain()
        pera = self.register_user()
        self.invite(pera)
        record = DomainRecord(domain=self.domain, record_type=self.types["A"], value={
            "name": "www", "address": "192.0.2.20", "ttl": 3600,
        })
        self.session.add(record)
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
