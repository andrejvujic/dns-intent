import base64
import binascii

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
