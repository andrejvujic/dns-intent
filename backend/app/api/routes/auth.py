from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.db.session import get_db
from app.models import User
from app.schemas import LoginRequest, LoginResponse, UserResponse


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
            detail="Pogrešan email ili lozinka.",
        )

    return LoginResponse(
        message="Uspješna prijava.",
        user=UserResponse.model_validate(user),
    )
