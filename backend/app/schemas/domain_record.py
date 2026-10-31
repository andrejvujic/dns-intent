import base64
import binascii
import re
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.domain_record import DEFAULT_DOMAIN_RECORD_TYPES


MAX_TTL = 2_147_483_647
DNS_TYPE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*$")
HEX_PATTERN = re.compile(r"^[0-9A-Fa-f]+$")
BASE32HEX_PATTERN = re.compile(r"^[0-9A-V]+$")


def normalize_dns_name(value: str) -> str:
    value = value.strip()
    if value == "@":
        return value

    value = value.rstrip(".")
    if not value or len(value) > 253:
        raise ValueError("DNS name must contain between 1 and 253 characters")

    normalized_labels: list[str] = []
    for index, label in enumerate(value.split(".")):
        if label == "*" and index == 0:
            normalized_labels.append(label)
            continue
        try:
            ascii_label = label.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("DNS name contains an invalid IDN label") from exc
        if len(ascii_label) > 63 or not re.fullmatch(
            r"[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?", ascii_label
        ):
            raise ValueError(f"Invalid DNS label: {label}")
        normalized_labels.append(ascii_label)

    return ".".join(normalized_labels)


def validate_base64(value: str, field_name: str) -> str:
    try:
        base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{field_name} must be valid Base64") from exc
    return value


class StrictRecordValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ttl: int = Field(ge=0, le=MAX_TTL)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_dns_name(value)


class ARecordValue(StrictRecordValue):
    address: IPv4Address


class AAAARecordValue(StrictRecordValue):
    address: IPv6Address


class CNAMERecordValue(StrictRecordValue):
    target: str

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        return normalize_dns_name(value)


class MXRecordValue(StrictRecordValue):
    exchange: str
    priority: int = Field(ge=0, le=65_535)

    @field_validator("exchange")
    @classmethod
    def validate_exchange(cls, value: str) -> str:
        return normalize_dns_name(value)


class TXTRecordValue(StrictRecordValue):
    text: str | list[str]

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str | list[str]) -> str | list[str]:
        chunks = [value] if isinstance(value, str) else value
        if not chunks:
            raise ValueError("TXT record must contain at least one text chunk")
        if any(not chunk or len(chunk.encode("utf-8")) > 255 for chunk in chunks):
            raise ValueError("Each TXT chunk must contain between 1 and 255 bytes")
        return value


class NSRecordValue(StrictRecordValue):
    host: str

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        return normalize_dns_name(value)


class DSRecordValue(StrictRecordValue):
    key_tag: int = Field(ge=0, le=65_535)
    algorithm: int = Field(ge=0, le=255)
    digest_type: int = Field(ge=0, le=255)
    digest: str

    @field_validator("digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        value = value.replace(" ", "").upper()
        if not value or len(value) % 2 or not HEX_PATTERN.fullmatch(value):
            raise ValueError("DS digest must contain an even number of hexadecimal digits")
        return value

    @model_validator(mode="after")
    def validate_digest_length(self) -> "DSRecordValue":
        expected_lengths = {1: 40, 2: 64, 4: 96}
        expected = expected_lengths.get(self.digest_type)
        if expected is not None and len(self.digest) != expected:
            raise ValueError(
                f"DS digest type {self.digest_type} requires {expected} hexadecimal digits"
            )
        return self


class DNSKEYRecordValue(StrictRecordValue):
    flags: int = Field(ge=0, le=65_535)
    protocol: int
    algorithm: int = Field(ge=0, le=255)
    public_key: str

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, value: int) -> int:
        if value != 3:
            raise ValueError("DNSKEY protocol must be 3")
        return value

    @field_validator("public_key")
    @classmethod
    def validate_public_key(cls, value: str) -> str:
        return validate_base64(value, "DNSKEY public_key")


class RRSIGRecordValue(StrictRecordValue):
    type_covered: str
    algorithm: int = Field(ge=0, le=255)
    labels: int = Field(ge=0, le=255)
    original_ttl: int = Field(ge=0, le=MAX_TTL)
    signature_expiration: str
    signature_inception: str
    key_tag: int = Field(ge=0, le=65_535)
    signer_name: str
    signature: str

    @field_validator("type_covered")
    @classmethod
    def validate_type_covered(cls, value: str) -> str:
        value = value.strip().upper()
        if not DNS_TYPE_PATTERN.fullmatch(value):
            raise ValueError("RRSIG type_covered must be a DNS record type")
        return value

    @field_validator("signature_expiration", "signature_inception")
    @classmethod
    def validate_dns_timestamp(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y%m%d%H%M%S")
        except ValueError as exc:
            raise ValueError("RRSIG time must use YYYYMMDDHHMMSS format") from exc
        return value

    @field_validator("signer_name")
    @classmethod
    def validate_signer_name(cls, value: str) -> str:
        return normalize_dns_name(value)

    @field_validator("signature")
    @classmethod
    def validate_signature(cls, value: str) -> str:
        return validate_base64(value, "RRSIG signature")


class NSECRecordValue(StrictRecordValue):
    next_domain_name: str
    types: list[str] = Field(min_length=1)

    @field_validator("next_domain_name")
    @classmethod
    def validate_next_domain_name(cls, value: str) -> str:
        return normalize_dns_name(value)

    @field_validator("types")
    @classmethod
    def validate_types(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip().upper() for value in values))
        if any(not DNS_TYPE_PATTERN.fullmatch(value) for value in normalized):
            raise ValueError("NSEC types must contain valid DNS record type names")
        return normalized


class NSEC3RecordValue(StrictRecordValue):
    hash_algorithm: int = Field(ge=0, le=255)
    flags: int = Field(ge=0, le=255)
    iterations: int = Field(ge=0, le=65_535)
    salt: str
    next_hashed_owner_name: str
    types: list[str] = Field(min_length=1)

    @field_validator("salt")
    @classmethod
    def validate_salt(cls, value: str) -> str:
        value = value.strip().upper()
        if value == "-":
            return value
        if len(value) % 2 or not HEX_PATTERN.fullmatch(value):
            raise ValueError("NSEC3 salt must be '-' or an even-length hexadecimal value")
        return value

    @field_validator("next_hashed_owner_name")
    @classmethod
    def validate_next_hash(cls, value: str) -> str:
        value = value.strip().upper()
        if not value or not BASE32HEX_PATTERN.fullmatch(value):
            raise ValueError("NSEC3 next hash must use unpadded Base32hex")
        return value

    @field_validator("types")
    @classmethod
    def validate_types(cls, values: list[str]) -> list[str]:
        return NSECRecordValue.validate_types(values)


class CAARecordValue(StrictRecordValue):
    flags: int
    tag: str
    value: str

    @field_validator("flags")
    @classmethod
    def validate_flags(cls, value: int) -> int:
        if value not in (0, 128):
            raise ValueError("CAA flags must be 0 or 128")
        return value

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9]+", value):
            raise ValueError("CAA tag must contain only ASCII letters and digits")
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        if not value:
            raise ValueError("CAA value must not be empty")
        return value


RECORD_VALUE_MODELS: dict[str, type[StrictRecordValue]] = {
    "A": ARecordValue,
    "AAAA": AAAARecordValue,
    "CNAME": CNAMERecordValue,
    "MX": MXRecordValue,
    "TXT": TXTRecordValue,
    "NS": NSRecordValue,
    "DS": DSRecordValue,
    "DNSKEY": DNSKEYRecordValue,
    "RRSIG": RRSIGRecordValue,
    "NSEC": NSECRecordValue,
    "NSEC3": NSEC3RecordValue,
    "CAA": CAARecordValue,
}


class DomainRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, max_length=30)
    value: dict[str, Any]

    @field_validator("type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().upper()


class DomainRecordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: dict[str, Any]


class MemberPublicKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    intent_public_key: str
    panic_public_key: str


class IntentEnforcementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    panic_quorum: int = Field(ge=1)
    delay_seconds: int = Field(ge=1800)
    protected_operations: list[str] = Field(min_length=1)
    public_keys: list[MemberPublicKeys] = Field(min_length=1)

    @field_validator("protected_operations")
    @classmethod
    def validate_protected_operations(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip().upper() for value in values))
        supported = set(DEFAULT_DOMAIN_RECORD_TYPES) - {"IE"}
        if any(value not in supported for value in normalized):
            raise ValueError(
                "protected_operations must contain only supported DNS record types "
                "(IE cannot be protected)"
            )
        return normalized


def validate_record_value(record_type: str, value: dict[str, Any]) -> dict[str, Any]:
    model = RECORD_VALUE_MODELS.get(record_type)
    if model is None:
        raise ValueError(f"Unsupported DNS record type: {record_type}")
    return model.model_validate(value).model_dump(mode="json")


__all__ = [
    "DomainRecordCreate",
    "DomainRecordUpdate",
    "IntentEnforcementCreate",
    "MemberPublicKeys",
    "RECORD_VALUE_MODELS",
    "validate_record_value",
]
