import hashlib
import json
from typing import Any


def canonical_json(data: Any) -> bytes:
    """Return the single JSON representation used for hashes and signatures."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def commitment_hash(intent: dict[str, Any], nonce: bytes) -> bytes:
    return hashlib.sha256(canonical_json(intent) + nonce).digest()
