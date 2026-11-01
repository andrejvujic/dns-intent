from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import MembershipStatus

if TYPE_CHECKING:
    from app.models.commit import Commit
    from app.models.domain_record import DomainRecord
    from app.models.panic import PanicRequest, PanicSignature
    from app.models.user import User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(253), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    registrar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user_memberships: Mapped[list[UserDomain]] = relationship(
        back_populates="domain", cascade="all, delete-orphan"
    )
    records: Mapped[list[DomainRecord]] = relationship(
        back_populates="domain", cascade="all, delete-orphan"
    )
    panic_requests: Mapped[list[PanicRequest]] = relationship(
        back_populates="domain", cascade="all, delete-orphan"
    )


class UserDomain(Base):
    __tablename__ = "user_domains"
    __table_args__ = (
        UniqueConstraint("user_id", "domain_id", name="uq_user_domains_user_domain"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE"), index=True
    )
    intent_public_key: Mapped[str | None] = mapped_column(String(44), nullable=True)
    panic_public_key: Mapped[str | None] = mapped_column(String(44), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Self-registered users start as PENDING until a majority of accepted
    # members of this domain votes them in.
    membership_status: Mapped[MembershipStatus] = mapped_column(
        Enum(
            MembershipStatus,
            name="membership_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        default=MembershipStatus.ACCEPTED,
        server_default=MembershipStatus.ACCEPTED.value,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="domain_memberships")
    domain: Mapped[Domain] = relationship(back_populates="user_memberships")
    commits: Mapped[list[Commit]] = relationship(
        back_populates="user_domain", cascade="all, delete-orphan"
    )
    panic_signatures: Mapped[list[PanicSignature]] = relationship(
        back_populates="user_domain", cascade="all, delete-orphan"
    )
    membership_votes: Mapped[list[MembershipVote]] = relationship(
        back_populates="applicant",
        cascade="all, delete-orphan",
        foreign_keys="MembershipVote.applicant_user_domain_id",
    )


class MembershipVote(Base):
    """One accepted member's vote on a pending membership request."""

    __tablename__ = "membership_votes"
    __table_args__ = (
        UniqueConstraint(
            "applicant_user_domain_id",
            "voter_user_domain_id",
            name="uq_membership_votes_applicant_voter",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_user_domain_id: Mapped[int] = mapped_column(
        ForeignKey("user_domains.id", ondelete="CASCADE"), index=True
    )
    voter_user_domain_id: Mapped[int] = mapped_column(
        ForeignKey("user_domains.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(6))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    applicant: Mapped[UserDomain] = relationship(
        back_populates="membership_votes", foreign_keys=[applicant_user_domain_id]
    )
    voter: Mapped[UserDomain] = relationship(foreign_keys=[voter_user_domain_id])
