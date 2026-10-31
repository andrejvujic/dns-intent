from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.domain import Domain


DEFAULT_DOMAIN_RECORD_TYPES = (
    "A",
    "AAAA",
    "CNAME",
    "MX",
    "TXT",
    "NS",
    "DS",
    "DNSKEY",
    "RRSIG",
    "NSEC",
    "NSEC3",
    "CAA",
    "IE",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DomainRecordType(Base):
    __tablename__ = "domain_record_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True, index=True)

    records: Mapped[list[DomainRecord]] = relationship(back_populates="record_type")


class DomainRecord(Base):
    __tablename__ = "domain_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_record_type_id: Mapped[int] = mapped_column(
        ForeignKey("domain_record_types.id", ondelete="RESTRICT"), index=True
    )
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE"), index=True
    )
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    record_type: Mapped[DomainRecordType] = relationship(back_populates="records")
    domain: Mapped[Domain] = relationship(back_populates="records")
