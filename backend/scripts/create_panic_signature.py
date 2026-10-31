#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from app.schemas.panic import PanicChange
from app.services.canonical import canonical_json
from scripts.create_commit import load_private_key


def main() -> None:
    parser = argparse.ArgumentParser(description="Sign a Panic Change JSON with an Ed25519 panic key")
    parser.add_argument("change", help="Path to Panic Change JSON, or - for stdin")
    parser.add_argument("--private-key", required=True, help="Base64 Ed25519 panic private key")
    parser.add_argument("-o", "--output", help="Write the signature bundle to a file")
    args = parser.parse_args()
    try:
        source = sys.stdin.read() if args.change == "-" else Path(args.change).read_text(encoding="utf-8")
        change = PanicChange.model_validate_json(source)
        data = change.model_dump(mode="json", exclude_none=True)
        digest = hashlib.sha256(canonical_json(data)).digest()
        signature = load_private_key(args.private_key).sign(digest)
        signature_b64 = base64.b64encode(signature).decode("ascii")
        bundle = {
            "format": "dns-intent-panic-signature-v1",
            "domain": change.domain,
            "request_id": change.request_id,
            "panic_request": {
                "hash": base64.b64encode(digest).decode("ascii"),
                "signature": signature_b64,
            },
            "signature": signature_b64,
        }
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
