from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas import LoginRequest, LoginResponse, RegisterRequest, UserResponse


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


@router.post(
    "/register",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterRequest, session: DbSession) -> LoginResponse:
    """Create the account only; domain members add the user to a domain by quorum vote."""
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

    user = User(
        first_name=payload.first_name,
        last_name=payload.last_name,
        username=payload.email,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return LoginResponse(
        message="Account created. Create your own domain, or ask a domain member to add you.",
        user=UserResponse.model_validate(user),
    )
