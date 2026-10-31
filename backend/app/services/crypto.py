import base64
import binascii

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class CryptoInputError(ValueError):
    pass


def decode_b64(value: str, *, field: str, expected_length: int | None = None) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CryptoInputError(f"{field} must be valid Base64") from exc
    if expected_length is not None and len(decoded) != expected_length:
        raise CryptoInputError(f"{field} must decode to {expected_length} bytes")
    return decoded


def validate_public_key(value: str, *, field: str) -> None:
    raw = decode_b64(value, field=field, expected_length=32)
    try:
        Ed25519PublicKey.from_public_bytes(raw)
    except ValueError as exc:
        raise CryptoInputError(f"{field} is not a valid Ed25519 public key") from exc


def verify_signature(public_key: str, signature: str, message: bytes) -> bool:
    try:
        key_bytes = decode_b64(
            public_key, field="intent_public_key", expected_length=32
        )
        signature_bytes = decode_b64(
            signature, field="signature", expected_length=64
        )
        Ed25519PublicKey.from_public_bytes(key_bytes).verify(
            signature_bytes, message
        )
    except (CryptoInputError, InvalidSignature, ValueError):
        return False
    return True
