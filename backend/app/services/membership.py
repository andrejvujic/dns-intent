from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Domain, MembershipStatus, User, UserDomain


def required_quorum(accepted_count: int) -> int:
    """Strict majority: more than half of the accepted members."""
    return accepted_count // 2 + 1


def accepted_memberships(domain_id: int, session: Session) -> list[UserDomain]:
    return list(
        session.scalars(
            select(UserDomain)
            .join(User, User.id == UserDomain.user_id)
            .where(
                UserDomain.domain_id == domain_id,
                UserDomain.is_active.is_(True),
                UserDomain.membership_status == MembershipStatus.ACCEPTED,
                User.is_active.is_(True),
            )
        ).all()
    )


def create_invitation(
    user: User, domain: Domain, inviter: UserDomain, session: Session,
    *, protected: bool,
) -> UserDomain:
    """Add immediately without protection, or start a protected invitation."""
    membership = session.scalar(
        select(UserDomain).where(
            UserDomain.user_id == user.id,
            UserDomain.domain_id == domain.id,
        )
    )
    if membership is None:
        membership = UserDomain(
            user=user,
            domain=domain,
            membership_status=MembershipStatus.PENDING if protected else MembershipStatus.ACCEPTED,
            invited_by_user_id=inviter.user_id,
        )
        session.add(membership)
    elif membership.membership_status != MembershipStatus.ACCEPTED:
        # A signed proposal may restart an expired or legacy unsigned invitation.
        # The caller must first reject any live ADD_MEMBER panic request.
        membership.membership_status = MembershipStatus.PENDING if protected else MembershipStatus.ACCEPTED
        membership.invited_by_user_id = inviter.user_id
        membership.is_active = True
        membership.created_at = datetime.now(timezone.utc)
        for vote in list(membership.membership_votes):
            session.delete(vote)
        session.flush()
        session.refresh(membership)
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user is already a member of the domain or already has a pending vote.",
        )
    session.flush()
    return membership
