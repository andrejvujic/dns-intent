from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models import Domain, User
from app.schemas import (
    LoginRequest,
    LoginResponse,
    PublicDomain,
    RegisterRequest,
    UserResponse,
)
from app.services.email import send_join_request_email
from app.services.membership import create_join_request, join_request_notification


router = APIRouter(prefix="/api/auth", tags=["authentication"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("/login", response_model=LoginResponse)
def login(credentials: LoginRequest, session: DbSession) -> LoginResponse:
    email = credentials.email.strip().lower()
    user = session.scalar(select(User).where(User.email == email))

    if (
        user is None
        or not user.is_active
        or not verify_password(credentials.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    return LoginResponse(
        message="Login successful.",
        user=UserResponse.model_validate(user),
    )


@router.get("/domains", response_model=list[PublicDomain])
def list_public_domains(session: DbSession) -> list[PublicDomain]:
    """Domains a new user can ask to join; only names, no records."""
    domains = session.scalars(select(Domain).order_by(Domain.name)).all()
    return [
        PublicDomain(id=domain.id, name=domain.name, description=domain.description)
        for domain in domains
    ]


@router.post(
    "/register",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    background_tasks: BackgroundTasks,
    session: DbSession,
) -> LoginResponse:
    existing = session.scalar(
        select(User.id).where(
            or_(User.email == payload.email, User.username == payload.email)
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    domain = session.get(Domain, payload.domain_id)
    if domain is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found.",
        )

    user = User(
        first_name=payload.first_name,
        last_name=payload.last_name,
        username=payload.email,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    session.flush()
    create_join_request(user, domain, session)
    recipients, notification = join_request_notification(user, domain, session)
    session.commit()
    session.refresh(user)

    background_tasks.add_task(send_join_request_email, recipients, notification)
    return LoginResponse(
        message="Account created. Your access is pending approval by the domain members.",
        user=UserResponse.model_validate(user),
    )
