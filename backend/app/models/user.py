from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.domain import UserDomain
    from app.models.panic import PanicRequest


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Self-registered users have no name; they are shown by their email instead.
    first_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    last_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    @property
    def display_name(self) -> str:
        """Name for emails and logs: full name when known, otherwise the email's local part."""
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.email.partition("@")[0]

    domain_memberships: Mapped[list[UserDomain]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    created_panic_requests: Mapped[list[PanicRequest]] = relationship(
        back_populates="created_by", foreign_keys="PanicRequest.created_by_user_id"
    )
