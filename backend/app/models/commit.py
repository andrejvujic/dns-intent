from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CommitStatus

if TYPE_CHECKING:
    from app.models.domain import UserDomain


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (
        CheckConstraint("length(hash) = 44", name="ck_commits_hash_length"),
        CheckConstraint("matures_at >= received_at", name="ck_commits_maturity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_domain_id: Mapped[int] = mapped_column(
        ForeignKey("user_domains.id", ondelete="CASCADE"), index=True
    )
    # Standard Base64 encoding of the 32-byte SHA-256 commitment digest.
    hash: Mapped[str] = mapped_column(String(44), unique=True, index=True)
    signature: Mapped[str] = mapped_column(String(88))
    status: Mapped[CommitStatus] = mapped_column(
        Enum(
            CommitStatus,
            name="commit_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        default=CommitStatus.HOLDING,
        nullable=False,
        index=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    matures_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user_domain: Mapped[UserDomain] = relationship(back_populates="commits")
