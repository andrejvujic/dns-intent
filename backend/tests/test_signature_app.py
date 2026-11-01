import base64
import json
import tempfile
from pathlib import Path
from unittest import TestCase

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.signature_app import NORMAL_SIGNATURE, PANIC_SIGNATURE, sign_file


class SignatureAppTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        private_key = Ed25519PrivateKey.generate()
        key_der = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        cls.private_key = base64.b64encode(key_der).decode("ascii")

    def test_creates_normal_signature_bundle(self) -> None:
        intent = {
            "domain": "example.test",
            "operation": "DELETE_RECORD",
            "record_id": 7,
            "not_before": "2026-11-01T12:00:00Z",
            "valid_until": "2026-11-01T13:00:00Z",
        }
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory, "intent.json")
            output_path = Path(directory, "signed.json")
            input_path.write_text(json.dumps(intent), encoding="utf-8")

            sign_file(NORMAL_SIGNATURE, str(input_path), str(output_path), self.private_key)

            bundle = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(bundle["format"], "dns-intent-signing-bundle-v2")
            self.assertEqual(bundle["intent_file"], "intent.json")
            self.assertIn("nonce", bundle["reveal_secret"])

    def test_creates_panic_signature_bundle(self) -> None:
        change = {
            "type": "PANIC_CHANGE",
            "request_id": "request-123",
            "domain": "example.test",
            "operation": "ROTATE_KEYS",
            "expires_at": "2026-11-01T13:00:00Z",
        }
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory, "panic.json")
            output_path = Path(directory, "signed.json")
            input_path.write_text(json.dumps(change), encoding="utf-8")

            sign_file(PANIC_SIGNATURE, str(input_path), str(output_path), self.private_key)

            bundle = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(bundle["format"], "dns-intent-panic-signature-v1")
            self.assertEqual(bundle["request_id"], "request-123")
            self.assertEqual(bundle["operation"], "ROTATE_KEYS")
            self.assertEqual(bundle["signature"], bundle["panic_request"]["signature"])

    def test_creates_member_removal_panic_signature_bundle(self) -> None:
        change = {
            "type": "PANIC_CHANGE",
            "request_id": "remove-member-123",
            "domain": "example.test",
            "operation": "REMOVE_MEMBER",
            "target_user_id": 42,
            "expires_at": "2026-11-02T13:00:00Z",
        }
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory, "remove-member-panic.json")
            output_path = Path(directory, "signed.json")
            input_path.write_text(json.dumps(change), encoding="utf-8")

            sign_file(PANIC_SIGNATURE, str(input_path), str(output_path), self.private_key)

            bundle = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(bundle["format"], "dns-intent-panic-signature-v1")
            self.assertEqual(bundle["operation"], "REMOVE_MEMBER")
            self.assertEqual(bundle["target_user_id"], 42)
            self.assertEqual(bundle["signature"], bundle["panic_request"]["signature"])

    def test_rejects_missing_output_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "output JSON"):
            sign_file(NORMAL_SIGNATURE, "intent.json", "", self.private_key)

    def test_does_not_overwrite_input_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory, "intent.json")
            input_path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be different"):
                sign_file(
                    NORMAL_SIGNATURE,
                    str(input_path),
                    str(input_path),
                    self.private_key,
                )
