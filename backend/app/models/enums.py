from enum import StrEnum


class CommitStatus(StrEnum):
    HOLDING = "HOLDING"
    READY = "READY"
    CONSUMED = "CONSUMED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PanicRequestStatus(StrEnum):
    PENDING = "PENDING"
    QUORUM_REACHED = "QUORUM_REACHED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PanicVoteDecision(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
