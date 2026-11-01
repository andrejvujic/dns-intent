#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.panic import PanicChange
from app.services.canonical import canonical_json
from scripts.create_commit import load_private_key


def read_panic_change(path: str) -> PanicChange:
    """Read and validate a panic change from a file (or stdin)."""
    source = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return PanicChange.model_validate_json(source)


def create_panic_bundle(change: PanicChange, private_key: Any) -> dict[str, Any]:
    """Create the same signature bundle used by the command-line interface."""
    data = change.model_dump(mode="json", exclude_none=True)
    digest = hashlib.sha256(canonical_json(data)).digest()
    signature = private_key.sign(digest)
    signature_b64 = base64.b64encode(signature).decode("ascii")
    bundle = {
        "format": "dns-intent-panic-signature-v1",
        "domain": change.domain,
        "request_id": change.request_id,
        "operation": change.operation,
        "panic_request": {
            "hash": base64.b64encode(digest).decode("ascii"),
            "signature": signature_b64,
        },
        "signature": signature_b64,
    }
    if change.operation == "REMOVE_MEMBER":
        bundle["target_user_id"] = change.target_user_id
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description="Sign a Panic Change JSON with an Ed25519 panic key")
    parser.add_argument("change", help="Path to Panic Change JSON, or - for stdin")
    parser.add_argument("--private-key", required=True, help="Base64 Ed25519 panic private key")
    parser.add_argument("-o", "--output", help="Write the signature bundle to a file")
    args = parser.parse_args()
    try:
        change = read_panic_change(args.change)
        bundle = create_panic_bundle(change, load_private_key(args.private_key))
    except (OSError, ValueError, ValidationError) as exc:
        parser.error(str(exc))
    output = f"{json.dumps(bundle, indent=2, ensure_ascii=False)}\n"
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Panic signature bundle written to {args.output}")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
