from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DomainSummary(BaseModel):
    id: int
    name: str
    description: str | None
    registrar: str | None
    record_count: int
    updated_at: datetime


class DomainRecordResponse(BaseModel):
    id: int
    type: str
    value: Any
    created_at: datetime
    updated_at: datetime


class DomainDetailResponse(DomainSummary):
    records: list[DomainRecordResponse]
