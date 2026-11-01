from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DomainSummary(BaseModel):
    id: int
    name: str
    description: str | None
    registrar: str | None
    record_count: int
    updated_at: datetime
    membership_status: str = "ACCEPTED"


class DomainRecordResponse(BaseModel):
    id: int
    type: str
    value: Any
    created_at: datetime
    updated_at: datetime


class DomainDetailResponse(DomainSummary):
    records: list[DomainRecordResponse]
    has_intent_keys: bool = False


class DomainMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    username: str
    email: str


class TeamMemberResponse(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    email: str
    membership_status: str
    has_intent_keys: bool


class MembershipRequestResponse(BaseModel):
    membership_id: int
    user_id: int
    first_name: str
    last_name: str
    email: str
    status: str
    for_count: int
    against_count: int
    required_quorum: int
    user_vote: str | None
    requested_at: datetime


class DomainTeamResponse(BaseModel):
    my_status: str
    accepted_count: int
    required_quorum: int
    members: list[TeamMemberResponse]
    requests: list[MembershipRequestResponse]


class MembershipVoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(ACCEPT|REJECT)$")


class OwnPublicKeysCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_public_key: str = Field(min_length=44, max_length=44)
    panic_public_key: str = Field(min_length=44, max_length=44)
