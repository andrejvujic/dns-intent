from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Domain, MembershipStatus, MembershipVote, User, UserDomain
from app.services.email import EmailRecipient, JoinRequestEmail


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
    user: User, domain: Domain, inviter: UserDomain, session: Session
) -> UserDomain:
    """Propose adding the user to the domain; the inviter's ACCEPT vote is recorded."""
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
            membership_status=MembershipStatus.PENDING,
        )
        session.add(membership)
    elif membership.membership_status == MembershipStatus.DECLINED:
        # A declined user may be proposed again; the old votes no longer count.
        membership.membership_status = MembershipStatus.PENDING
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
    record_membership_vote(membership, inviter, "ACCEPT", session)
    return membership


def invitation_notification(
    user: User, domain: Domain, inviter: User, session: Session
) -> tuple[list[EmailRecipient], JoinRequestEmail]:
    members = accepted_memberships(domain.id, session)
    recipients = [
        EmailRecipient(email=member.user.email, first_name=member.user.display_name)
        for member in members
    ]
    notification = JoinRequestEmail(
        domain_name=domain.name,
        applicant_name=user.display_name,
        applicant_email=user.email,
        invited_by=inviter.display_name,
        required_quorum=required_quorum(len(members)),
        requested_at=datetime.now(timezone.utc),
    )
    return recipients, notification


def tally_membership_votes(applicant: UserDomain, session: Session) -> None:
    """Accept or decline once a strict majority of accepted members agrees."""
    voters = {member.id for member in accepted_memberships(applicant.domain_id, session)}
    quorum = required_quorum(len(voters))
    votes = [vote for vote in applicant.membership_votes if vote.voter_user_domain_id in voters]
    accepts = sum(vote.decision == "ACCEPT" for vote in votes)
    rejects = sum(vote.decision == "REJECT" for vote in votes)
    if accepts >= quorum:
        applicant.membership_status = MembershipStatus.ACCEPTED
    elif rejects >= quorum:
        applicant.membership_status = MembershipStatus.DECLINED


def record_membership_vote(
    applicant: UserDomain, voter: UserDomain, decision: str, session: Session
) -> None:
    if applicant.membership_status != MembershipStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This membership request is no longer pending.",
        )
    if any(vote.voter_user_domain_id == voter.id for vote in applicant.membership_votes):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already voted on this request.",
        )
    applicant.membership_votes.append(
        MembershipVote(voter_user_domain_id=voter.id, decision=decision)
    )
    session.flush()
    tally_membership_votes(applicant, session)
