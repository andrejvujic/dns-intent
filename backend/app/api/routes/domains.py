import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import (
    Commit,
    CommitStatus,
    Domain,
    DomainRecord,
    DomainRecordType,
    MembershipStatus,
    MembershipVote,
    User,
    UserDomain,
    PanicRequest,
    PanicRequestStatus,
    PanicSignature,
    PanicVoteDecision,
)
from app.schemas import (
    CommitApplyResponse,
    CommitCreate,
    CommitResponse,
    CommitReveal,
    DomainCreate,
    DomainDetailResponse,
    DomainMemberResponse,
    DomainRecordCreate,
    DomainRecordResponse,
    DomainRecordUpdate,
    DomainSummary,
    DomainTeamResponse,
    Intent,
    IntentEnforcementCreate,
    InvitationCreate,
    InviteCandidateResponse,
    MembershipRequestResponse,
    MembershipVoteCreate,
    OwnPublicKeysCreate,
    PanicCreate,
    PanicResponse,
    PanicSignatureCreate,
    PanicVoteCreate,
    RotationKeysCreate,
    TeamMemberResponse,
)
from app.schemas.domain_record import validate_record_value
from app.services.canonical import canonical_json, commitment_hash
from app.services.crypto import (
    CryptoInputError,
    decode_b64,
    validate_public_key,
    verify_signature,
)
from app.services.email import (
    EmailRecipient,
    PanicChangeEmail,
    ScheduledIntentEmail,
    send_join_request_email,
    send_panic_change_email,
    send_scheduled_intent_email,
)
from app.services.membership import (
    accepted_memberships,
    create_invitation,
    invitation_notification,
    record_membership_vote,
    required_quorum,
)


router = APIRouter(prefix="/api/users/{user_id}/domains", tags=["domains"])
DbSession = Annotated[Session, Depends(get_db)]


def to_summary(
    domain: Domain, membership_status: MembershipStatus = MembershipStatus.ACCEPTED
) -> DomainSummary:
    return DomainSummary(
        id=domain.id,
        name=domain.name,
        description=domain.description,
        registrar=domain.registrar,
        record_count=len(domain.records),
        updated_at=domain.updated_at,
        membership_status=MembershipStatus(membership_status).value,
    )


def to_record_response(record: DomainRecord) -> DomainRecordResponse:
    return DomainRecordResponse(
        id=record.id,
        type=record.record_type.name,
        value=record.value,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def get_authorized_domain(user_id: int, domain_id: int, session: Session) -> Domain:
    domain = session.scalar(
        select(Domain)
        .join(UserDomain)
        .join(User, User.id == UserDomain.user_id)
        .where(
            Domain.id == domain_id,
            UserDomain.user_id == user_id,
            UserDomain.is_active.is_(True),
            UserDomain.membership_status != MembershipStatus.DECLINED,
            User.is_active.is_(True),
        )
    )
    if domain is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found or the user has no access to it.",
        )
    return domain


def get_active_membership(
    user_id: int, domain_id: int, session: Session
) -> UserDomain:
    membership = session.scalar(
        select(UserDomain)
        .join(User, User.id == UserDomain.user_id)
        .where(
            UserDomain.user_id == user_id,
            UserDomain.domain_id == domain_id,
            UserDomain.is_active.is_(True),
            User.is_active.is_(True),
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found or the user has no access to it.",
        )
    if membership.membership_status != MembershipStatus.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your membership in this domain is pending approval by the domain quorum.",
        )
    return membership


def find_membership(user_id: int, domain_id: int, session: Session) -> UserDomain | None:
    return session.scalar(
        select(UserDomain).where(
            UserDomain.user_id == user_id,
            UserDomain.domain_id == domain_id,
        )
    )


def ensure_can_edit_records(user_id: int, domain: Domain, session: Session) -> None:
    """Anyone with access may edit an unprotected domain; a protected one needs approval."""
    membership = find_membership(user_id, domain.id, session)
    if (
        membership is not None
        and membership.membership_status != MembershipStatus.ACCEPTED
        and find_ie_record(domain.id, session) is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This domain is protected by DNS Intent. You can change it only after "
                "a majority of its members accepts your membership."
            ),
        )


def commit_response(
    commit: Commit,
    user: User,
    *,
    cancellation_pending: bool = False,
    cancellation_panic_id: int | None = None,
) -> CommitResponse:
    return CommitResponse(
        id=commit.id,
        hash=commit.hash,
        status=commit.status.value,
        received_at=commit.received_at,
        matures_at=commit.matures_at,
        consumed_at=commit.consumed_at,
        user_id=user.id,
        username=user.username,
        cancellation_pending=cancellation_pending,
        cancellation_panic_id=cancellation_panic_id,
    )


def pending_cancellation_for_commit(
    domain_id: int, commit_id: int, session: Session
) -> PanicRequest | None:
    now = datetime.now(timezone.utc)
    requests = session.scalars(
        select(PanicRequest).where(
            PanicRequest.domain_id == domain_id,
            PanicRequest.operation == "CANCEL_COMMIT",
            PanicRequest.status == PanicRequestStatus.PENDING,
        )
    ).all()
    for request in requests:
        expires_at = request.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > now and (request.change_json or {}).get("commit_id") == commit_id:
            return request
    return None


def panic_response(request: PanicRequest, user_id: int) -> PanicResponse:
    votes = {vote.user_domain.user_id: vote for vote in request.signatures}
    current_vote = votes.get(user_id)
    return PanicResponse(
        id=request.id,
        request_id=request.request_id,
        domain_id=request.domain_id,
        created_by_user_id=request.created_by_user_id,
        created_by_username=request.created_by.username,
        change=request.change_json,
        hash=request.hash,
        required_quorum=request.required_quorum,
        for_count=sum(vote.decision == PanicVoteDecision.ACCEPT for vote in request.signatures),
        against_count=sum(vote.decision == PanicVoteDecision.REJECT for vote in request.signatures),
        user_has_signed=current_vote is not None and current_vote.is_valid,
        user_vote=current_vote.decision.value if current_vote and current_vote.decision else None,
        status=request.status.value,
        expires_at=request.expires_at,
        applied_at=request.applied_at,
        created_at=request.created_at,
    )


def find_ie_record(domain_id: int, session: Session) -> DomainRecord | None:
    return session.scalar(
        select(DomainRecord)
        .join(DomainRecordType)
        .where(
            DomainRecord.domain_id == domain_id,
            DomainRecordType.name == "IE",
        )
        .limit(1)
    )


def get_protected_operations(domain_id: int, session: Session) -> set[str]:
    ie_record = find_ie_record(domain_id, session)
    if ie_record is None:
        return set()

    operations = (ie_record.value or {}).get("protected_operations", [])
    return {str(operation).upper() for operation in operations}


def ensure_intent_not_enabled(domain_id: int, session: Session) -> None:
    if find_ie_record(domain_id, session) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="DNS Intent is already enabled for this domain.",
        )


def ensure_type_mutable(
    record_type_name: str, domain_id: int, session: Session
) -> None:
    if record_type_name in get_protected_operations(domain_id, session):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"DNS record type {record_type_name} is protected by DNS Intent. "
                "Use the commit/reveal or panic flow."
            ),
        )


def validated_value(record_type: str, value: dict) -> dict:
    try:
        return validate_record_value(record_type, value)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.errors(include_url=False),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


def ensure_record_is_unique(
    session: Session,
    domain_id: int,
    record_type_id: int,
    value: dict,
    *,
    exclude_record_id: int | None = None,
) -> None:
    records = session.scalars(
        select(DomainRecord).where(
            DomainRecord.domain_id == domain_id,
            DomainRecord.domain_record_type_id == record_type_id,
        )
    ).all()
    if any(
        record.id != exclude_record_id and record.value == value for record in records
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An identical DNS record already exists.",
        )


def validated_rotation_keys(
    domain_id: int,
    public_keys: list,
    session: Session,
) -> dict[int, tuple[str, str]]:
    memberships = accepted_memberships(domain_id, session)
    expected_ids = {membership.user_id for membership in memberships}
    normalized: dict[int, tuple[str, str]] = {}
    for item in public_keys:
        if isinstance(item, dict):
            user_id = item.get("user_id")
            intent_public_key = item.get("intent_public_key")
            panic_public_key = item.get("panic_public_key")
        else:
            user_id = item.user_id
            intent_public_key = item.intent_public_key
            panic_public_key = item.panic_public_key
        if user_id in normalized:
            raise HTTPException(status_code=422, detail="Rotation contains duplicate users.")
        try:
            validate_public_key(intent_public_key, field=f"user {user_id} intent_public_key")
            validate_public_key(panic_public_key, field=f"user {user_id} panic_public_key")
        except CryptoInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        normalized[user_id] = (intent_public_key, panic_public_key)

    if set(normalized) != expected_ids:
        raise HTTPException(
            status_code=422,
            detail="New public keys are required for every active domain member.",
        )
    return normalized


def delete_domain_change_requests(
    domain_id: int,
    session: Session,
    *,
    preserve_panic_request_id: int | None,
) -> None:
    scheduled_commits = session.scalars(
        select(Commit)
        .join(UserDomain, Commit.user_domain_id == UserDomain.id)
        .where(UserDomain.domain_id == domain_id)
    ).all()
    for commit in scheduled_commits:
        session.delete(commit)

    panic_query = select(PanicRequest).where(PanicRequest.domain_id == domain_id)
    if preserve_panic_request_id is not None:
        panic_query = panic_query.where(PanicRequest.id != preserve_panic_request_id)
    for panic_request in session.scalars(panic_query).all():
        session.delete(panic_request)


@router.get("", response_model=list[DomainSummary])
def list_user_domains(user_id: int, session: DbSession) -> list[DomainSummary]:
    rows = session.execute(
        select(Domain, UserDomain.membership_status)
        .join(UserDomain)
        .where(
            UserDomain.user_id == user_id,
            UserDomain.is_active.is_(True),
            UserDomain.membership_status != MembershipStatus.DECLINED,
        )
        .options(selectinload(Domain.records))
        .order_by(Domain.name)
    ).all()

    return [to_summary(domain, membership_status) for domain, membership_status in rows]


@router.post("", response_model=DomainSummary, status_code=status.HTTP_201_CREATED)
def create_domain(user_id: int, payload: DomainCreate, session: DbSession) -> DomainSummary:
    """Any user may add a domain; the creator is its first accepted member."""
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found.")
    if session.scalar(select(Domain.id).where(Domain.name == payload.name)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A domain with this name already exists.",
        )
    domain = Domain(
        name=payload.name,
        description=payload.description,
        registrar=payload.registrar,
    )
    domain.user_memberships.append(
        UserDomain(user=user, membership_status=MembershipStatus.ACCEPTED)
    )
    session.add(domain)
    session.commit()
    session.refresh(domain)
    return to_summary(domain, MembershipStatus.ACCEPTED)


@router.get("/{domain_id}", response_model=DomainDetailResponse)
def get_user_domain(
    user_id: int, domain_id: int, session: DbSession
) -> DomainDetailResponse:
    domain = session.scalar(
        select(Domain)
        .join(UserDomain)
        .where(
            Domain.id == domain_id,
            UserDomain.user_id == user_id,
            UserDomain.is_active.is_(True),
            UserDomain.membership_status != MembershipStatus.DECLINED,
        )
        .options(
            selectinload(Domain.records).joinedload(DomainRecord.record_type)
        )
    )

    if domain is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found.",
        )

    membership = find_membership(user_id, domain.id, session)
    summary = to_summary(domain, membership.membership_status)
    return DomainDetailResponse(
        **summary.model_dump(),
        has_intent_keys=membership.intent_public_key is not None,
        records=[
            to_record_response(record)
            for record in sorted(
                domain.records, key=lambda item: (item.record_type.name, item.id)
            )
        ],
    )


@router.get("/{domain_id}/members", response_model=list[DomainMemberResponse])
def list_domain_members(
    user_id: int, domain_id: int, session: DbSession
) -> list[DomainMemberResponse]:
    get_authorized_domain(user_id, domain_id, session)

    members = session.scalars(
        select(User)
        .join(UserDomain)
        .where(
            UserDomain.domain_id == domain_id,
            UserDomain.is_active.is_(True),
            UserDomain.membership_status == MembershipStatus.ACCEPTED,
            User.is_active.is_(True),
        )
        .order_by(User.first_name, User.last_name)
    ).all()

    return [DomainMemberResponse.model_validate(member) for member in members]


@router.post(
    "/{domain_id}/records",
    response_model=DomainRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_domain_record(
    user_id: int,
    domain_id: int,
    payload: DomainRecordCreate,
    session: DbSession,
) -> DomainRecordResponse:
    domain = get_authorized_domain(user_id, domain_id, session)
    ensure_can_edit_records(user_id, domain, session)

    if payload.type == "IE":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="IE records cannot be created through the regular DNS record endpoint.",
        )

    record_type = session.scalar(
        select(DomainRecordType).where(DomainRecordType.name == payload.type)
    )
    if record_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported DNS record type: {payload.type}",
        )

    ensure_type_mutable(record_type.name, domain.id, session)

    value = validated_value(record_type.name, payload.value)
    ensure_record_is_unique(session, domain.id, record_type.id, value)

    record = DomainRecord(domain=domain, record_type=record_type, value=value)
    session.add(record)
    session.commit()
    session.refresh(record)
    return to_record_response(record)


@router.post(
    "/{domain_id}/intent",
    response_model=DomainRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def enable_dns_intent(
    user_id: int,
    domain_id: int,
    payload: IntentEnforcementCreate,
    session: DbSession,
) -> DomainRecordResponse:
    domain = get_authorized_domain(user_id, domain_id, session)
    get_active_membership(user_id, domain_id, session)
    ensure_intent_not_enabled(domain.id, session)

    memberships = accepted_memberships(domain.id, session)
    expected_ids = {membership.user_id for membership in memberships}
    supplied_ids = [item.user_id for item in payload.public_keys]
    if (
        len(supplied_ids) != len(set(supplied_ids))
        or set(supplied_ids) != expected_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Public intent and panic keys are required for every active domain member.",
        )
    keys_by_user = {item.user_id: item for item in payload.public_keys}
    try:
        for membership in memberships:
            keys = keys_by_user[membership.user_id]
            validate_public_key(
                keys.intent_public_key,
                field=f"user {membership.user_id} intent_public_key",
            )
            validate_public_key(
                keys.panic_public_key,
                field=f"user {membership.user_id} panic_public_key",
            )
            membership.intent_public_key = keys.intent_public_key
            membership.panic_public_key = keys.panic_public_key
    except CryptoInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    record_type = session.scalar(
        select(DomainRecordType).where(DomainRecordType.name == "IE")
    )
    if record_type is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The IE record type is not configured in the system.",
        )

    value = {
        "name": "@",
        "ttl": 3600,
        "panic_quorum": payload.panic_quorum,
        "delay_seconds": payload.delay_seconds,
        "protected_operations": payload.protected_operations,
    }

    record = DomainRecord(domain=domain, record_type=record_type, value=value)
    session.add(record)
    session.commit()
    session.refresh(record)
    return to_record_response(record)


@router.post(
    "/{domain_id}/commits",
    response_model=CommitResponse,
    status_code=status.HTTP_201_CREATED,
)
def schedule_commit(
    user_id: int,
    domain_id: int,
    payload: CommitCreate,
    background_tasks: BackgroundTasks,
    session: DbSession,
) -> CommitResponse:
    domain = get_authorized_domain(user_id, domain_id, session)
    membership = get_active_membership(user_id, domain_id, session)
    ie_record = find_ie_record(domain.id, session)
    if ie_record is None or membership.intent_public_key is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="DNS Intent is not enabled for this domain.",
        )

    try:
        digest = decode_b64(payload.hash, field="hash", expected_length=32)
        decode_b64(payload.signature, field="signature", expected_length=64)
    except CryptoInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if not verify_signature(membership.intent_public_key, payload.signature, digest):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Signature is not valid for the signed-in user's Intent key.",
        )
    if session.scalar(select(Commit.id).where(Commit.hash == payload.hash)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This commitment hash has already been scheduled.",
        )

    now = datetime.now(timezone.utc)
    delay_seconds = int((ie_record.value or {}).get("delay_seconds", 0))
    matures_at = now + timedelta(seconds=delay_seconds)
    commit = Commit(
        user_domain=membership,
        hash=payload.hash,
        signature=payload.signature,
        status=CommitStatus.READY if delay_seconds == 0 else CommitStatus.HOLDING,
        received_at=now,
        matures_at=matures_at,
    )
    session.add(commit)
    session.commit()
    session.refresh(commit)
    user = session.get(User, user_id)
    recipients = session.scalars(
        select(User)
        .join(UserDomain)
        .where(
            UserDomain.domain_id == domain.id,
            UserDomain.is_active.is_(True),
            User.is_active.is_(True),
        )
        .order_by(User.id)
    ).all()
    background_tasks.add_task(
        send_scheduled_intent_email,
        [
            EmailRecipient(email=recipient.email, first_name=recipient.display_name)
            for recipient in recipients
        ],
        ScheduledIntentEmail(
            domain_name=domain.name,
            scheduled_by=user.display_name,
            commit_hash=commit.hash,
            received_at=commit.received_at,
            matures_at=commit.matures_at,
        ),
    )
    return commit_response(commit, user)


@router.get(
    "/{domain_id}/commits",
    response_model=list[CommitResponse],
)
def list_scheduled_commits(
    user_id: int, domain_id: int, session: DbSession
) -> list[CommitResponse]:
    get_authorized_domain(user_id, domain_id, session)
    now = datetime.now(timezone.utc)
    rows = session.execute(
        select(Commit, User)
        .join(UserDomain, Commit.user_domain_id == UserDomain.id)
        .join(User, User.id == UserDomain.user_id)
        .where(UserDomain.domain_id == domain_id)
        .order_by(Commit.received_at.desc())
    ).all()

    changed = False
    for commit, _ in rows:
        maturity = commit.matures_at
        if maturity.tzinfo is None:
            maturity = maturity.replace(tzinfo=timezone.utc)
        if commit.status == CommitStatus.HOLDING and maturity <= now:
            commit.status = CommitStatus.READY
            changed = True
    if changed:
        session.commit()

    responses = []
    for commit, user in rows:
        cancellation = pending_cancellation_for_commit(domain_id, commit.id, session)
        responses.append(
            commit_response(
                commit,
                user,
                cancellation_pending=cancellation is not None,
                cancellation_panic_id=cancellation.id if cancellation else None,
            )
        )
    return responses


def load_panic_request(
    request_id: int, domain_id: int, session: Session
) -> PanicRequest:
    request = session.scalar(
        select(PanicRequest)
        .where(PanicRequest.id == request_id, PanicRequest.domain_id == domain_id)
        .options(
            selectinload(PanicRequest.created_by),
            selectinload(PanicRequest.signatures)
            .selectinload(PanicSignature.user_domain),
        )
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Panic change was not found.")
    now = datetime.now(timezone.utc)
    expires_at = request.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if request.status == PanicRequestStatus.PENDING and now > expires_at:
        request.status = PanicRequestStatus.EXPIRED
        session.commit()
    return request


@router.post(
    "/{domain_id}/panic-changes",
    response_model=PanicResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_panic_change(
    user_id: int,
    domain_id: int,
    payload: PanicCreate,
    background_tasks: BackgroundTasks,
    session: DbSession,
) -> PanicResponse:
    domain = get_authorized_domain(user_id, domain_id, session)
    membership = get_active_membership(user_id, domain_id, session)
    ie_record = find_ie_record(domain.id, session)
    if ie_record is None or membership.panic_public_key is None:
        raise HTTPException(status_code=409, detail="DNS Intent is not enabled for this domain.")
    if payload.change.domain != domain.name.lower().rstrip("."):
        raise HTTPException(status_code=400, detail="Panic change domain does not match this domain.")
    expires_at = payload.change.expires_at.astimezone(timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Panic change has already expired.")
    change_data = payload.change.model_dump(mode="json", exclude_none=True)
    digest = hashlib.sha256(canonical_json(change_data)).digest()
    calculated_hash = base64.b64encode(digest).decode("ascii")
    try:
        supplied_hash = decode_b64(payload.hash, field="hash", expected_length=32) if payload.hash else None
        decode_b64(payload.signature, field="signature", expected_length=64)
    except CryptoInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if supplied_hash is not None and not hmac.compare_digest(digest, supplied_hash):
        raise HTTPException(status_code=403, detail="The supplied hash does not match the panic JSON.")
    if not verify_signature(membership.panic_public_key, payload.signature, digest):
        raise HTTPException(status_code=403, detail="Signature is not valid for the user's panic key.")
    if session.scalar(select(PanicRequest.id).where(PanicRequest.request_id == payload.change.request_id)):
        raise HTTPException(status_code=409, detail="This panic request_id has already been used.")
    if session.scalar(select(PanicRequest.id).where(PanicRequest.hash == calculated_hash)):
        raise HTTPException(status_code=409, detail="This panic change has already been submitted.")

    if payload.change.operation == "CANCEL_COMMIT":
        target_commit = session.scalar(
            select(Commit)
            .join(UserDomain, Commit.user_domain_id == UserDomain.id)
            .where(
                Commit.id == payload.change.commit_id,
                UserDomain.domain_id == domain.id,
            )
        )
        if target_commit is None:
            raise HTTPException(status_code=404, detail="Scheduled commit was not found.")
        if target_commit.status not in (CommitStatus.HOLDING, CommitStatus.READY):
            raise HTTPException(status_code=409, detail="Only an active scheduled commit can be cancelled.")
        if pending_cancellation_for_commit(domain.id, target_commit.id, session):
            raise HTTPException(status_code=409, detail="This commit already has a pending cancellation vote.")

    if payload.change.operation == "DISABLE_DNS_INTENT":
        shutdown_requests = session.scalars(
            select(PanicRequest).where(
                PanicRequest.domain_id == domain.id,
                PanicRequest.operation == "DISABLE_DNS_INTENT",
                PanicRequest.status == PanicRequestStatus.PENDING,
            )
        ).all()
        now = datetime.now(timezone.utc)
        pending_shutdown = False
        for shutdown_request in shutdown_requests:
            shutdown_expires_at = shutdown_request.expires_at
            if shutdown_expires_at.tzinfo is None:
                shutdown_expires_at = shutdown_expires_at.replace(tzinfo=timezone.utc)
            if shutdown_expires_at > now:
                pending_shutdown = True
            else:
                shutdown_request.status = PanicRequestStatus.EXPIRED
        if pending_shutdown:
            raise HTTPException(
                status_code=409,
                detail="DNS Intent already has a pending shutdown vote.",
            )

    if payload.change.operation == "ROTATE_KEYS":
        rotation_requests = session.scalars(
            select(PanicRequest).where(
                PanicRequest.domain_id == domain.id,
                PanicRequest.operation == "ROTATE_KEYS",
                PanicRequest.status == PanicRequestStatus.PENDING,
            )
        ).all()
        now = datetime.now(timezone.utc)
        for rotation_request in rotation_requests:
            rotation_expires_at = rotation_request.expires_at
            if rotation_expires_at.tzinfo is None:
                rotation_expires_at = rotation_expires_at.replace(tzinfo=timezone.utc)
            if rotation_expires_at > now:
                raise HTTPException(
                    status_code=409,
                    detail="This domain already has a pending key rotation vote.",
                )
            rotation_request.status = PanicRequestStatus.EXPIRED

    quorum = int((ie_record.value or {}).get("panic_quorum", 1))
    request = PanicRequest(
        request_id=payload.change.request_id,
        domain_id=domain.id,
        created_by_user_id=user_id,
        operation=payload.change.operation,
        value=change_data,
        change_json=change_data,
        hash=calculated_hash,
        creator_signature=payload.signature,
        required_quorum=quorum,
        expires_at=expires_at,
        status=PanicRequestStatus.PENDING,
    )
    session.add(request)
    session.flush()
    session.add(
        PanicSignature(
            panic_request_id=request.id,
            user_domain_id=membership.id,
            signature=payload.signature,
            is_valid=True,
            decision=PanicVoteDecision.ACCEPT,
        )
    )
    if quorum == 1:
        request.status = PanicRequestStatus.QUORUM_REACHED
        if request.operation != "ROTATE_KEYS":
            apply_panic_change(
                domain,
                change_data,
                session,
                preserve_panic_request_id=request.id,
            )
            request.status = PanicRequestStatus.APPLIED
            request.applied_at = datetime.now(timezone.utc)
    session.commit()
    creator = session.get(User, user_id)
    recipients = session.scalars(
        select(User)
        .join(UserDomain)
        .where(
            UserDomain.domain_id == domain.id,
            UserDomain.is_active.is_(True),
            User.is_active.is_(True),
        )
        .order_by(User.id)
    ).all()
    background_tasks.add_task(
        send_panic_change_email,
        [
            EmailRecipient(email=recipient.email, first_name=recipient.display_name)
            for recipient in recipients
        ],
        PanicChangeEmail(
            domain_name=domain.name,
            requested_by=creator.display_name,
            request_id=request.request_id,
            operation=request.operation,
            required_quorum=request.required_quorum,
            expires_at=request.expires_at,
            applied_immediately=request.status == PanicRequestStatus.APPLIED,
        ),
    )
    return panic_response(load_panic_request(request.id, domain.id, session), user_id)


@router.get("/{domain_id}/panic-changes", response_model=list[PanicResponse])
def list_panic_changes(
    user_id: int, domain_id: int, session: DbSession
) -> list[PanicResponse]:
    get_authorized_domain(user_id, domain_id, session)
    ids = session.scalars(
        select(PanicRequest.id)
        .where(PanicRequest.domain_id == domain_id)
        .order_by(PanicRequest.created_at.desc())
    ).all()
    return [panic_response(load_panic_request(item, domain_id, session), user_id) for item in ids]


@router.post(
    "/{domain_id}/panic-changes/{panic_id}/signatures",
    response_model=PanicResponse,
)
def attach_panic_signature(
    user_id: int,
    domain_id: int,
    panic_id: int,
    payload: PanicSignatureCreate,
    session: DbSession,
) -> PanicResponse:
    get_authorized_domain(user_id, domain_id, session)
    membership = get_active_membership(user_id, domain_id, session)
    request = load_panic_request(panic_id, domain_id, session)
    if request.status != PanicRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail="This panic change is no longer pending.")
    if membership.panic_public_key is None:
        raise HTTPException(status_code=409, detail="The user has no panic public key.")
    digest = decode_b64(request.hash, field="stored hash", expected_length=32)
    if not verify_signature(membership.panic_public_key, payload.signature, digest):
        raise HTTPException(status_code=403, detail="Signature is not valid for the user's panic key.")
    existing = session.scalar(
        select(PanicSignature).where(
            PanicSignature.panic_request_id == request.id,
            PanicSignature.user_domain_id == membership.id,
        )
    )
    if existing:
        if existing.signature != payload.signature:
            raise HTTPException(status_code=409, detail="A different signature is already attached.")
    else:
        session.add(PanicSignature(
            panic_request_id=request.id,
            user_domain_id=membership.id,
            signature=payload.signature,
            is_valid=True,
        ))
        session.commit()
    return panic_response(load_panic_request(request.id, domain_id, session), user_id)


@router.post(
    "/{domain_id}/panic-changes/{panic_id}/vote",
    response_model=PanicResponse,
)
def vote_on_panic_change(
    user_id: int,
    domain_id: int,
    panic_id: int,
    payload: PanicVoteCreate,
    session: DbSession,
) -> PanicResponse:
    domain = get_authorized_domain(user_id, domain_id, session)
    membership = get_active_membership(user_id, domain_id, session)
    request = load_panic_request(panic_id, domain_id, session)
    if request.status != PanicRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail="This panic change is no longer pending.")
    vote = session.scalar(
        select(PanicSignature).where(
            PanicSignature.panic_request_id == request.id,
            PanicSignature.user_domain_id == membership.id,
        )
    )
    if vote is None or not vote.is_valid or vote.signature != payload.signature:
        raise HTTPException(status_code=403, detail="Attach this valid panic signature before voting.")
    if membership.panic_public_key is None or not verify_signature(
        membership.panic_public_key,
        payload.signature,
        decode_b64(request.hash, field="stored hash", expected_length=32),
    ):
        raise HTTPException(status_code=403, detail="The panic signature is no longer valid.")
    if vote.decision is not None:
        raise HTTPException(status_code=409, detail="This user has already voted.")

    vote.decision = PanicVoteDecision(payload.decision)
    session.flush()
    votes = session.scalars(
        select(PanicSignature).where(PanicSignature.panic_request_id == request.id)
    ).all()
    for_count = sum(item.decision == PanicVoteDecision.ACCEPT for item in votes)
    against_count = sum(item.decision == PanicVoteDecision.REJECT for item in votes)
    if for_count >= request.required_quorum:
        request.status = PanicRequestStatus.QUORUM_REACHED
        if request.operation != "ROTATE_KEYS":
            apply_panic_change(
                domain,
                request.change_json,
                session,
                preserve_panic_request_id=request.id,
            )
            request.status = PanicRequestStatus.APPLIED
            request.applied_at = datetime.now(timezone.utc)
    elif against_count >= request.required_quorum:
        request.status = PanicRequestStatus.REJECTED
    session.commit()
    return panic_response(load_panic_request(request.id, domain_id, session), user_id)


@router.post(
    "/{domain_id}/panic-changes/{panic_id}/rotation-keys",
    response_model=PanicResponse,
)
def finalize_key_rotation(
    user_id: int,
    domain_id: int,
    panic_id: int,
    payload: RotationKeysCreate,
    session: DbSession,
) -> PanicResponse:
    domain = get_authorized_domain(user_id, domain_id, session)
    request = load_panic_request(panic_id, domain_id, session)
    if request.operation != "ROTATE_KEYS":
        raise HTTPException(status_code=409, detail="This panic request is not a key rotation.")
    if request.status != PanicRequestStatus.QUORUM_REACHED:
        raise HTTPException(
            status_code=409,
            detail="New keys can be generated only after the rotation quorum is reached.",
        )
    if request.created_by_user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Only the user who initiated this rotation can generate and apply the new keys.",
        )

    keys_by_user = validated_rotation_keys(domain.id, payload.public_keys, session)
    apply_key_rotation(
        domain,
        keys_by_user,
        session,
        preserve_panic_request_id=request.id,
    )
    request.status = PanicRequestStatus.APPLIED
    request.applied_at = datetime.now(timezone.utc)
    session.commit()
    return panic_response(load_panic_request(request.id, domain_id, session), user_id)


@router.post(
    "/{domain_id}/commits/{commit_id}/reveal",
    response_model=CommitApplyResponse,
)
def reveal_and_apply_commit(
    user_id: int,
    domain_id: int,
    commit_id: int,
    payload: CommitReveal,
    session: DbSession,
) -> CommitApplyResponse:
    domain = get_authorized_domain(user_id, domain_id, session)
    commit = session.scalar(
        select(Commit)
        .join(UserDomain, Commit.user_domain_id == UserDomain.id)
        .where(Commit.id == commit_id, UserDomain.domain_id == domain.id)
        .options(
            selectinload(Commit.user_domain).joinedload(UserDomain.user)
        )
    )
    if commit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled commit was not found.",
        )
    if commit.status == CommitStatus.CONSUMED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This commit has already been applied.",
        )
    if commit.status in (CommitStatus.REJECTED, CommitStatus.EXPIRED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This commit was cancelled or expired and cannot be revealed.",
        )
    cancellation = pending_cancellation_for_commit(domain.id, commit.id, session)
    if cancellation is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Commit application is temporarily blocked by pending panic "
                f"cancellation #{cancellation.id}. It can be applied only if that cancellation is rejected or expires."
            ),
        )

    now = datetime.now(timezone.utc)
    matures_at = commit.matures_at
    if matures_at.tzinfo is None:
        matures_at = matures_at.replace(tzinfo=timezone.utc)
    if now < matures_at:
        raise HTTPException(
            status_code=status.HTTP_425_TOO_EARLY,
            detail=f"The hold period ends at {matures_at.isoformat()}.",
        )
    if payload.intent.domain != domain.name.lower().rstrip("."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Intent domain does not match this domain.",
        )
    not_before = payload.intent.not_before.astimezone(timezone.utc)
    valid_until = payload.intent.valid_until.astimezone(timezone.utc)
    if now < not_before:
        raise HTTPException(
            status_code=status.HTTP_425_TOO_EARLY,
            detail=(
                "The intent is not active yet: "
                f"current UTC time is {now.isoformat()}, "
                f"not_before is {not_before.isoformat()}."
            ),
        )
    if now > valid_until:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="The intent has expired.",
        )

    try:
        nonce = decode_b64(payload.nonce, field="nonce")
    except CryptoInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if len(nonce) < 16:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="nonce must decode to at least 16 bytes",
        )

    intent_data = payload.intent.model_dump(mode="json", exclude_none=True)
    calculated_hash = commitment_hash(intent_data, nonce)
    stored_hash = decode_b64(commit.hash, field="stored hash", expected_length=32)
    if not hmac.compare_digest(calculated_hash, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Intent and nonce do not match the scheduled commit hash.",
        )

    record_id = apply_intent(domain, payload.intent, session)
    commit.status = CommitStatus.CONSUMED
    commit.consumed_at = now
    session.commit()
    session.refresh(commit)
    return CommitApplyResponse(
        status="applied",
        commit=commit_response(commit, commit.user_domain.user),
        record_id=record_id,
    )


def apply_intent(domain: Domain, intent: Intent, session: Session) -> int | None:
    operation = intent.operation
    if operation == "ADD_RECORD":
        if intent.record_type not in get_protected_operations(domain.id, session):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This record type is not protected; use the regular DNS endpoint.",
            )
        record_type = session.scalar(
            select(DomainRecordType).where(DomainRecordType.name == intent.record_type)
        )
        if record_type is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unsupported DNS record type: {intent.record_type}",
            )
        value = validated_value(record_type.name, intent.value)
        ensure_record_is_unique(session, domain.id, record_type.id, value)
        record = DomainRecord(domain=domain, record_type=record_type, value=value)
        session.add(record)
        session.flush()
        return record.id

    record = session.scalar(
        select(DomainRecord)
        .where(DomainRecord.id == intent.record_id, DomainRecord.domain_id == domain.id)
        .options(selectinload(DomainRecord.record_type))
    )
    if record is None or record.record_type.name == "IE":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DNS record from the intent was not found.",
        )
    if record.record_type.name not in get_protected_operations(domain.id, session):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This record type is not protected; use the regular DNS endpoint.",
        )

    if operation == "UPDATE_RECORD":
        value = validated_value(record.record_type.name, intent.value)
        ensure_record_is_unique(
            session,
            domain.id,
            record.domain_record_type_id,
            value,
            exclude_record_id=record.id,
        )
        record.value = value
        return record.id

    session.delete(record)
    return None


def apply_panic_change(
    domain: Domain,
    change: dict,
    session: Session,
    *,
    preserve_panic_request_id: int | None = None,
) -> int | None:
    operation = change["operation"]
    if operation == "DISABLE_DNS_INTENT":
        ie_record = find_ie_record(domain.id, session)
        if ie_record is None:
            raise HTTPException(status_code=409, detail="DNS Intent is not enabled for this domain.")

        delete_domain_change_requests(
            domain.id,
            session,
            preserve_panic_request_id=preserve_panic_request_id,
        )
        session.delete(ie_record)

        memberships = session.scalars(
            select(UserDomain).where(UserDomain.domain_id == domain.id)
        ).all()
        for membership in memberships:
            membership.intent_public_key = None
            membership.panic_public_key = None
        return None

    if operation == "ROTATE_KEYS":
        raise HTTPException(
            status_code=409,
            detail="Key rotation must be finalized with new keys after quorum approval.",
        )

    if operation == "CANCEL_COMMIT":
        commit = session.scalar(
            select(Commit)
            .join(UserDomain, Commit.user_domain_id == UserDomain.id)
            .where(
                Commit.id == change["commit_id"],
                UserDomain.domain_id == domain.id,
            )
        )
        if commit is None:
            raise HTTPException(status_code=404, detail="Scheduled commit was not found.")
        if commit.status not in (CommitStatus.HOLDING, CommitStatus.READY):
            raise HTTPException(status_code=409, detail="Only an active scheduled commit can be cancelled.")
        commit.status = CommitStatus.REJECTED
        return None

    if operation == "ADD_RECORD":
        record_type_name = change["record_type"]
        if record_type_name not in get_protected_operations(domain.id, session):
            raise HTTPException(status_code=409, detail="This record type is not protected.")
        record_type = session.scalar(
            select(DomainRecordType).where(DomainRecordType.name == record_type_name)
        )
        if record_type is None:
            raise HTTPException(status_code=422, detail=f"Unsupported DNS record type: {record_type_name}")
        value = validated_value(record_type.name, change["value"])
        ensure_record_is_unique(session, domain.id, record_type.id, value)
        record = DomainRecord(domain=domain, record_type=record_type, value=value)
        session.add(record)
        session.flush()
        return record.id

    record = session.scalar(
        select(DomainRecord)
        .where(DomainRecord.id == change["record_id"], DomainRecord.domain_id == domain.id)
        .options(selectinload(DomainRecord.record_type))
    )
    if record is None or record.record_type.name == "IE":
        raise HTTPException(status_code=404, detail="DNS record from the panic change was not found.")
    if record.record_type.name not in get_protected_operations(domain.id, session):
        raise HTTPException(status_code=409, detail="This record type is not protected.")
    if operation == "UPDATE_RECORD":
        value = validated_value(record.record_type.name, change["value"])
        ensure_record_is_unique(
            session,
            domain.id,
            record.domain_record_type_id,
            value,
            exclude_record_id=record.id,
        )
        record.value = value
        return record.id
    session.delete(record)
    return None


def apply_key_rotation(
    domain: Domain,
    keys_by_user: dict[int, tuple[str, str]],
    session: Session,
    *,
    preserve_panic_request_id: int,
) -> None:
    delete_domain_change_requests(
        domain.id,
        session,
        preserve_panic_request_id=preserve_panic_request_id,
    )
    memberships = session.scalars(
        select(UserDomain).where(UserDomain.domain_id == domain.id)
    ).all()
    for membership in memberships:
        keys = keys_by_user.get(membership.user_id)
        if membership.is_active and keys is not None:
            membership.intent_public_key, membership.panic_public_key = keys
        else:
            membership.intent_public_key = None
            membership.panic_public_key = None


@router.patch(
    "/{domain_id}/records/{record_id}",
    response_model=DomainRecordResponse,
)
def update_domain_record(
    user_id: int,
    domain_id: int,
    record_id: int,
    payload: DomainRecordUpdate,
    session: DbSession,
) -> DomainRecordResponse:
    domain = get_authorized_domain(user_id, domain_id, session)
    ensure_can_edit_records(user_id, domain, session)

    record = session.scalar(
        select(DomainRecord)
        .where(DomainRecord.id == record_id, DomainRecord.domain_id == domain.id)
        .options(selectinload(DomainRecord.record_type))
    )
    if record is None or record.record_type.name == "IE":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DNS record not found.",
        )

    ensure_type_mutable(record.record_type.name, domain.id, session)

    value = validated_value(record.record_type.name, payload.value)
    ensure_record_is_unique(
        session,
        domain.id,
        record.domain_record_type_id,
        value,
        exclude_record_id=record.id,
    )
    record.value = value
    session.commit()
    session.refresh(record)
    return to_record_response(record)


@router.delete(
    "/{domain_id}/records/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_domain_record(
    user_id: int,
    domain_id: int,
    record_id: int,
    session: DbSession,
) -> Response:
    domain = get_authorized_domain(user_id, domain_id, session)
    ensure_can_edit_records(user_id, domain, session)

    record = session.scalar(
        select(DomainRecord)
        .join(DomainRecordType)
        .where(
            DomainRecord.id == record_id,
            DomainRecord.domain_id == domain.id,
            DomainRecordType.name != "IE",
        )
        .options(selectinload(DomainRecord.record_type))
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DNS record not found.",
        )

    ensure_type_mutable(record.record_type.name, domain.id, session)

    session.delete(record)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def build_team_response(domain: Domain, user_id: int, session: Session) -> DomainTeamResponse:
    memberships = session.scalars(
        select(UserDomain)
        .join(User, User.id == UserDomain.user_id)
        .where(
            UserDomain.domain_id == domain.id,
            UserDomain.is_active.is_(True),
            User.is_active.is_(True),
        )
        .options(
            selectinload(UserDomain.user),
            selectinload(UserDomain.membership_votes)
            .joinedload(MembershipVote.voter)
            .joinedload(UserDomain.user),
        )
        .order_by(User.first_name, User.last_name)
    ).all()
    accepted = [m for m in memberships if m.membership_status == MembershipStatus.ACCEPTED]
    accepted_ids = {m.id for m in accepted}
    quorum = required_quorum(len(accepted))
    me = next((m for m in memberships if m.user_id == user_id), None)

    requests = []
    for membership in memberships:
        if membership.membership_status != MembershipStatus.PENDING:
            continue
        votes = [v for v in membership.membership_votes if v.voter_user_domain_id in accepted_ids]
        my_vote = next(
            (v.decision for v in votes if me is not None and v.voter_user_domain_id == me.id),
            None,
        )
        # The inviter's ACCEPT is always the first vote on an invitation.
        first_vote = min(membership.membership_votes, key=lambda v: v.id, default=None)
        requests.append(
            MembershipRequestResponse(
                membership_id=membership.id,
                user_id=membership.user_id,
                first_name=membership.user.first_name,
                last_name=membership.user.last_name,
                email=membership.user.email,
                status=membership.membership_status.value,
                for_count=sum(v.decision == "ACCEPT" for v in votes),
                against_count=sum(v.decision == "REJECT" for v in votes),
                required_quorum=quorum,
                user_vote=my_vote,
                invited_by=first_vote.voter.user.display_name if first_vote else None,
                requested_at=membership.created_at,
            )
        )

    return DomainTeamResponse(
        my_status=me.membership_status.value if me else MembershipStatus.PENDING.value,
        accepted_count=len(accepted),
        required_quorum=quorum,
        members=[
            TeamMemberResponse(
                user_id=m.user_id,
                first_name=m.user.first_name,
                last_name=m.user.last_name,
                email=m.user.email,
                membership_status=m.membership_status.value,
                has_intent_keys=m.intent_public_key is not None,
            )
            for m in memberships
            if m.membership_status != MembershipStatus.DECLINED
        ],
        requests=requests,
    )


@router.get("/{domain_id}/team", response_model=DomainTeamResponse)
def get_domain_team(user_id: int, domain_id: int, session: DbSession) -> DomainTeamResponse:
    domain = get_authorized_domain(user_id, domain_id, session)
    return build_team_response(domain, user_id, session)


@router.post(
    "/{domain_id}/membership-requests/{membership_id}/vote",
    response_model=DomainTeamResponse,
)
def vote_on_membership_request(
    user_id: int,
    domain_id: int,
    membership_id: int,
    payload: MembershipVoteCreate,
    session: DbSession,
) -> DomainTeamResponse:
    domain = get_authorized_domain(user_id, domain_id, session)
    voter = get_active_membership(user_id, domain_id, session)
    applicant = session.scalar(
        select(UserDomain)
        .where(UserDomain.id == membership_id, UserDomain.domain_id == domain.id)
        .options(selectinload(UserDomain.membership_votes))
    )
    if applicant is None:
        raise HTTPException(status_code=404, detail="Membership request was not found.")
    if applicant.id == voter.id:
        raise HTTPException(status_code=403, detail="You cannot vote on your own request.")
    record_membership_vote(applicant, voter, payload.decision, session)
    session.commit()
    return build_team_response(domain, user_id, session)


@router.post("/{domain_id}/my-keys", response_model=DomainTeamResponse)
def register_own_keys(
    user_id: int,
    domain_id: int,
    payload: OwnPublicKeysCreate,
    session: DbSession,
) -> DomainTeamResponse:
    """A member accepted after DNS Intent was enabled adds keys made on their own device."""
    domain = get_authorized_domain(user_id, domain_id, session)
    membership = get_active_membership(user_id, domain_id, session)
    if find_ie_record(domain.id, session) is None:
        raise HTTPException(status_code=409, detail="DNS Intent is not enabled for this domain.")
    if membership.intent_public_key is not None or membership.panic_public_key is not None:
        raise HTTPException(
            status_code=409,
            detail="Your keys are already registered. Use key rotation to replace them.",
        )
    try:
        validate_public_key(payload.intent_public_key, field="intent_public_key")
        validate_public_key(payload.panic_public_key, field="panic_public_key")
    except CryptoInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    membership.intent_public_key = payload.intent_public_key
    membership.panic_public_key = payload.panic_public_key
    session.commit()
    return build_team_response(domain, user_id, session)


@router.get("/{domain_id}/candidates", response_model=list[InviteCandidateResponse])
def list_invite_candidates(
    user_id: int, domain_id: int, session: DbSession
) -> list[InviteCandidateResponse]:
    """Registered users who are not (and are not being voted) into this domain."""
    get_authorized_domain(user_id, domain_id, session)
    get_active_membership(user_id, domain_id, session)
    taken = select(UserDomain.user_id).where(
        UserDomain.domain_id == domain_id,
        UserDomain.membership_status != MembershipStatus.DECLINED,
    )
    users = session.scalars(
        select(User)
        .where(User.is_active.is_(True), User.id.not_in(taken))
        .order_by(User.created_at.desc(), User.email)
    ).all()
    return [
        InviteCandidateResponse(
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
        )
        for user in users
    ]


@router.post(
    "/{domain_id}/invitations",
    response_model=DomainTeamResponse,
    status_code=status.HTTP_201_CREATED,
)
def invite_to_domain(
    user_id: int,
    domain_id: int,
    payload: InvitationCreate,
    background_tasks: BackgroundTasks,
    session: DbSession,
) -> DomainTeamResponse:
    """An accepted member proposes a user; a majority of accepted members decides."""
    domain = get_authorized_domain(user_id, domain_id, session)
    inviter = get_active_membership(user_id, domain_id, session)
    invitee = session.get(User, payload.user_id)
    if invitee is None or not invitee.is_active:
        raise HTTPException(status_code=404, detail="User not found.")
    create_invitation(invitee, domain, inviter, session)
    recipients, notification = invitation_notification(invitee, domain, inviter.user, session)
    session.commit()
    background_tasks.add_task(send_join_request_email, recipients, notification)
    return build_team_response(domain, user_id, session)
