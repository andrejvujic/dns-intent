import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import password_policy_errors


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def normalized_email(value: str) -> str:
    normalized = value.strip().lower()
    if not EMAIL_PATTERN.match(normalized):
        raise ValueError("must be a valid email address")
    return normalized


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    # The email is also the username, so it must fit the username column.
    email: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1, max_length=255)

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalized_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        errors = password_policy_errors(value)
        if errors:
            raise ValueError("password needs " + ", ".join(errors))
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    username: str
    email: str


class LoginResponse(BaseModel):
    message: str
    user: UserResponse

