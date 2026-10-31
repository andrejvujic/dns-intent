from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.domain_record import MemberPublicKeys, validate_record_value


PANIC_OPERATIONS = {
    "ADD_RECORD",
    "UPDATE_RECORD",
    "DELETE_RECORD",
    "CANCEL_COMMIT",
    "DISABLE_DNS_INTENT",
    "ROTATE_KEYS",
}


class PanicChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["PANIC_CHANGE"] = "PANIC_CHANGE"
    request_id: str = Field(min_length=8, max_length=128)
    domain: str = Field(min_length=1, max_length=253)
    operation: str = Field(min_length=1, max_length=50)
    record_type: str | None = Field(default=None, min_length=1, max_length=30)
    record_id: int | None = Field(default=None, gt=0)
    commit_id: int | None = Field(default=None, gt=0)
    value: dict[str, Any] | None = None
    expires_at: datetime

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        return value.strip().lower().rstrip(".")

    @field_validator("operation")
    @classmethod
    def normalize_operation(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in PANIC_OPERATIONS:
            raise ValueError("unsupported panic operation")
        return normalized

    @field_validator("record_type")
    @classmethod
    def normalize_record_type(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @model_validator(mode="after")
    def validate_change(self) -> "PanicChange":
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        if self.operation == "DISABLE_DNS_INTENT":
            if any((self.record_type, self.record_id, self.commit_id, self.value)):
                raise ValueError("DISABLE_DNS_INTENT does not accept record or commit fields")
            return self
        if self.operation == "ROTATE_KEYS":
            if any((self.record_type, self.record_id, self.commit_id, self.value)):
                raise ValueError("ROTATE_KEYS does not accept record or commit fields")
            return self
        if self.operation == "CANCEL_COMMIT":
            if self.commit_id is None:
                raise ValueError("CANCEL_COMMIT requires commit_id")
            if any((self.record_type, self.record_id, self.value)):
                raise ValueError("CANCEL_COMMIT only accepts commit_id")
            return self
        if self.commit_id is not None:
            raise ValueError("commit_id is only valid for CANCEL_COMMIT")
        if self.operation == "ADD_RECORD":
            if self.record_type is None or self.value is None or self.record_id is not None:
                raise ValueError("ADD_RECORD requires record_type and value")
            if self.record_type == "IE":
                raise ValueError("IE records cannot be created through panic changes")
            self.value = validate_record_value(self.record_type, self.value)
        elif self.operation == "UPDATE_RECORD":
            if self.record_id is None or self.value is None or self.record_type is not None:
                raise ValueError("UPDATE_RECORD requires record_id and value")
        elif self.operation == "DELETE_RECORD":
            if self.record_id is None or self.record_type is not None or self.value is not None:
                raise ValueError("DELETE_RECORD only accepts record_id")
        return self


class PanicCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    change: PanicChange
    hash: str | None = Field(default=None, min_length=44, max_length=44)
    signature: str = Field(min_length=88, max_length=88)


class PanicSignatureCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signature: str = Field(min_length=88, max_length=88)


class PanicVoteCreate(PanicSignatureCreate):
    decision: Literal["ACCEPT", "REJECT"]


class RotationKeysCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    public_keys: list[MemberPublicKeys] = Field(min_length=1)


class PanicResponse(BaseModel):
    id: int
    request_id: str
    domain_id: int
    created_by_user_id: int
    created_by_username: str
    change: dict[str, Any]
    hash: str
    required_quorum: int
    for_count: int
    against_count: int
    user_has_signed: bool
    user_vote: str | None
    status: str
    expires_at: datetime
    applied_at: datetime | None
    created_at: datetime
