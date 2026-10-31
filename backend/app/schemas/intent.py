from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.domain_record import validate_record_value


SUPPORTED_OPERATIONS = {"ADD_RECORD", "UPDATE_RECORD", "DELETE_RECORD"}


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str = Field(min_length=1, max_length=253)
    operation: str = Field(min_length=1, max_length=50)
    record_type: str | None = Field(default=None, min_length=1, max_length=30)
    record_id: int | None = Field(default=None, gt=0)
    value: dict[str, Any] | None = None
    not_before: datetime
    valid_until: datetime

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        normalized = value.strip().lower().rstrip(".")
        if not normalized:
            raise ValueError("domain must not be empty")
        return normalized

    @field_validator("operation")
    @classmethod
    def normalize_operation(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in SUPPORTED_OPERATIONS:
            raise ValueError(
                "operation must be ADD_RECORD, UPDATE_RECORD, or DELETE_RECORD"
            )
        return normalized

    @field_validator("record_type")
    @classmethod
    def normalize_record_type(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @model_validator(mode="after")
    def validate_intent(self) -> "Intent":
        if self.not_before.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("not_before and valid_until must include a timezone")
        if self.valid_until <= self.not_before:
            raise ValueError("valid_until must be after not_before")

        if self.operation == "ADD_RECORD":
            if self.record_type is None:
                raise ValueError("ADD_RECORD requires record_type")
            if self.record_id is not None:
                raise ValueError("ADD_RECORD must not contain record_id")
            if self.value is None:
                raise ValueError("ADD_RECORD requires value")
            if self.record_type == "IE":
                raise ValueError("IE records cannot be created through an intent")
            self.value = validate_record_value(self.record_type, self.value)

        elif self.operation == "UPDATE_RECORD":
            if self.record_id is None:
                raise ValueError("UPDATE_RECORD requires record_id")
            if self.record_type is not None:
                raise ValueError(
                    "UPDATE_RECORD must not contain record_type; a record's type cannot change"
                )
            if self.value is None:
                raise ValueError("UPDATE_RECORD requires value")

        elif self.operation == "DELETE_RECORD":
            if self.record_id is None:
                raise ValueError("DELETE_RECORD requires record_id")
            if self.record_type is not None:
                raise ValueError("DELETE_RECORD must not contain record_type")
            if self.value is not None:
                raise ValueError("DELETE_RECORD must not contain value")

        return self
