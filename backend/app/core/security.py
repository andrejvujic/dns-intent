import bcrypt


BCRYPT_ROUNDS = 12
BCRYPT_MAX_PASSWORD_BYTES = 72


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
