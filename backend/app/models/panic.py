from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import PanicRequestStatus, PanicVoteDecision

if TYPE_CHECKING:
    from app.models.domain import Domain, UserDomain
    from app.models.user import User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PanicRequest(Base):
    __tablename__ = "panic_requests"
    __table_args__ = (
        CheckConstraint("required_quorum >= 1", name="ck_panic_requests_quorum"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    operation: Mapped[str] = mapped_column(String(50))
    change_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    hash: Mapped[str] = mapped_column(String(44), unique=True, index=True)
    creator_signature: Mapped[str] = mapped_column(String(88))
    value: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    required_quorum: Mapped[int] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[PanicRequestStatus] = mapped_column(
        Enum(
            PanicRequestStatus,
            name="panic_request_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        default=PanicRequestStatus.PENDING,
        nullable=False,
        index=True,
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    domain: Mapped[Domain] = relationship(back_populates="panic_requests")
    created_by: Mapped[User] = relationship(
        back_populates="created_panic_requests", foreign_keys=[created_by_user_id]
    )
    signatures: Mapped[list[PanicSignature]] = relationship(
        back_populates="panic_request", cascade="all, delete-orphan"
    )


class PanicSignature(Base):
    __tablename__ = "panic_signatures"
    __table_args__ = (
        UniqueConstraint(
            "panic_request_id",
            "user_domain_id",
            name="uq_panic_signatures_request_membership",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    panic_request_id: Mapped[int] = mapped_column(
        ForeignKey("panic_requests.id", ondelete="CASCADE"), index=True
    )
    user_domain_id: Mapped[int] = mapped_column(
        ForeignKey("user_domains.id", ondelete="CASCADE"), index=True
    )
    signature: Mapped[str] = mapped_column(String(88))
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    decision: Mapped[PanicVoteDecision | None] = mapped_column(
        Enum(
            PanicVoteDecision,
            name="panic_vote_decision",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    panic_request: Mapped[PanicRequest] = relationship(back_populates="signatures")
    user_domain: Mapped[UserDomain] = relationship(back_populates="panic_signatures")
