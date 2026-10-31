from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.intent import Intent


class CommitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hash: str = Field(min_length=44, max_length=44)
    signature: str = Field(min_length=88, max_length=88)


class CommitResponse(BaseModel):
    id: int
    hash: str
    status: str
    received_at: datetime
    matures_at: datetime
    consumed_at: datetime | None
    user_id: int
    username: str
    cancellation_pending: bool = False
    cancellation_panic_id: int | None = None


class CommitReveal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    nonce: str = Field(min_length=24)


class CommitApplyResponse(BaseModel):
    status: str
    commit: CommitResponse
    record_id: int | None = None

