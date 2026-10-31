#!/usr/bin/env python3
import argparse
import base64
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def pair() -> dict[str, str]:
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return {
        "private_key": base64.b64encode(private_raw).decode(),
        "public_key": base64.b64encode(public_raw).decode(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Ed25519 keys for DNSIntent")
    parser.add_argument("--count", type=int, default=3)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be at least 1")
    print(json.dumps({"intent": [pair() for _ in range(args.count)], "recovery": [pair() for _ in range(args.count)]}, indent=2))


if __name__ == "__main__":
    main()
