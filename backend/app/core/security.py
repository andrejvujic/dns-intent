import re

import bcrypt


BCRYPT_ROUNDS = 12
BCRYPT_MAX_PASSWORD_BYTES = 72
PASSWORD_MIN_LENGTH = 10

# Same rules the sign-up form shows live; keep both lists in sync.
PASSWORD_RULES = (
    (lambda value: len(value) >= PASSWORD_MIN_LENGTH, f"at least {PASSWORD_MIN_LENGTH} characters"),
    (lambda value: re.search(r"[A-Z]", value) is not None, "an uppercase letter"),
    (lambda value: re.search(r"[a-z]", value) is not None, "a lowercase letter"),
    (lambda value: re.search(r"[0-9]", value) is not None, "a number"),
    (lambda value: re.search(r"[^A-Za-z0-9\s]", value) is not None, "a special character"),
    (lambda value: re.search(r"\s", value) is None, "no spaces"),
)


def password_policy_errors(password: str) -> list[str]:
    errors = [message for check, message in PASSWORD_RULES if not check(password)]
    if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        errors.append(f"at most {BCRYPT_MAX_PASSWORD_BYTES} bytes")
    return errors


def _password_bytes(password: str) -> bytes:
    encoded = password.encode("utf-8")
    if not encoded:
        raise ValueError("Password must not be empty")
    if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password must not exceed {BCRYPT_MAX_PASSWORD_BYTES} UTF-8 bytes"
        )
    return encoded


def hash_password(password: str) -> str:
    password_bytes = _password_bytes(password)
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(password_bytes, salt).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        password_bytes = _password_bytes(password)
        return bcrypt.checkpw(password_bytes, password_hash.encode("ascii"))
    except (TypeError, ValueError, UnicodeEncodeError):
        return False
