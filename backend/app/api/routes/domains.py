from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.session import get_db
from app.models import Domain, DomainRecord, UserDomain
from app.schemas import DomainDetailResponse, DomainRecordResponse, DomainSummary


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
            detail="Domen nije pronađen.",
        )

    summary = to_summary(domain)
    return DomainDetailResponse(
        **summary.model_dump(),
        records=[
            DomainRecordResponse(
                id=record.id,
                type=record.record_type.name,
                value=record.value,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            for record in sorted(
                domain.records, key=lambda item: (item.record_type.name, item.id)
            )
        ],
    )
