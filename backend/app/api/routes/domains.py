from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import Domain, DomainRecord, DomainRecordType, User, UserDomain
from app.schemas import (
    DomainDetailResponse,
    DomainMemberResponse,
    DomainRecordCreate,
    DomainRecordResponse,
    DomainRecordUpdate,
    DomainSummary,
    IntentEnforcementCreate,
)
from app.schemas.domain_record import validate_record_value
from app.services.crypto import CryptoInputError, validate_public_key


router = APIRouter(prefix="/api/users/{user_id}/domains", tags=["domains"])
DbSession = Annotated[Session, Depends(get_db)]


def to_summary(domain: Domain) -> DomainSummary:
    return DomainSummary(
        id=domain.id,
        name=domain.name,
        description=domain.description,
        registrar=domain.registrar,
        record_count=len(domain.records),
        updated_at=domain.updated_at,
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
            User.is_active.is_(True),
        )
    )
    if domain is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found or the user has no access to it.",
        )
    return domain


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


@router.get("", response_model=list[DomainSummary])
def list_user_domains(user_id: int, session: DbSession) -> list[DomainSummary]:
    domains = session.scalars(
        select(Domain)
        .join(UserDomain)
        .where(UserDomain.user_id == user_id, UserDomain.is_active.is_(True))
        .options(selectinload(Domain.records))
        .order_by(Domain.name)
    ).all()

    return [to_summary(domain) for domain in domains]


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

    summary = to_summary(domain)
    return DomainDetailResponse(
        **summary.model_dump(),
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
    ensure_intent_not_enabled(domain.id, session)

    memberships = session.scalars(
        select(UserDomain).where(
            UserDomain.domain_id == domain.id,
            UserDomain.is_active.is_(True),
        )
    ).all()
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
