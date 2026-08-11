"""Age-encrypted cross-run runtime auth transport. Never logs plaintext secrets."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from runtime_auth import _atomic_secret_json, HAPPYHORSE_SESSION, VOLCENGINE_CREDENTIAL

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENCRYPTED_AUTH_DIR = PROJECT_ROOT / "runtime-auth"
ENCRYPTED_BUNDLE = ENCRYPTED_AUTH_DIR / "runtime-auth.v1.age"
PUBLIC_KEY_FILE = ENCRYPTED_AUTH_DIR / "runtime-auth-public-key.txt"
SCHEMA_VERSION = 1


def _age_binary() -> str:
    binary = shutil.which("age")
    if not binary:
        raise RuntimeError("age binary unavailable")
    return binary


def validate_bundle(payload: dict) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("unsupported runtime auth bundle schema")
    volc = payload.get("volcengine")
    hh = payload.get("happyhorse")
    if not isinstance(volc, dict) or not str(volc.get("api_key", "")).strip():
        raise RuntimeError("Volcengine credential missing")
    if not isinstance(hh, dict):
        raise RuntimeError("HappyHorse session missing")
    access = hh.get("accessToken") or hh.get("access_token")
    refresh = hh.get("refreshToken") or hh.get("refresh_token")
    if not access and not refresh:
        raise RuntimeError("HappyHorse access/refresh token missing")


def decrypt_bundle(*, encrypted: Path = ENCRYPTED_BUNDLE, identity_file: Path) -> dict:
    proc = subprocess.run(
        [_age_binary(), "--decrypt", "--identity", str(identity_file), str(encrypted)],
        check=True, capture_output=True,
    )
    payload = json.loads(proc.stdout.decode("utf-8"))
    validate_bundle(payload)
    return payload


def materialize_bundle(payload: dict) -> None:
    validate_bundle(payload)
    _atomic_secret_json(VOLCENGINE_CREDENTIAL, {"api_key": payload["volcengine"]["api_key"]})
    _atomic_secret_json(HAPPYHORSE_SESSION, payload["happyhorse"])


def decrypt_and_materialize(*, encrypted: Path = ENCRYPTED_BUNDLE, identity_file: Path) -> None:
    materialize_bundle(decrypt_bundle(encrypted=encrypted, identity_file=identity_file))


def encrypt_bundle(*, payload: dict, recipient: str, output: Path = ENCRYPTED_BUNDLE) -> None:
    validate_bundle(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
        plaintext = Path(handle.name)
    tmp = output.with_suffix(output.suffix + ".new")
    try:
        subprocess.run(
            [_age_binary(), "--encrypt", "--recipient", recipient, "--output", str(tmp), str(plaintext)],
            check=True, capture_output=True,
        )
        os.replace(tmp, output)
    finally:
        plaintext.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)


def bundle_from_materialized() -> dict:
    volc = json.loads(VOLCENGINE_CREDENTIAL.read_text(encoding="utf-8"))
    hh = json.loads(HAPPYHORSE_SESSION.read_text(encoding="utf-8"))
    payload = {"schema_version": SCHEMA_VERSION, "volcengine": volc, "happyhorse": hh}
    validate_bundle(payload)
    return payload


def reencrypt_materialized(*, recipient: str, output: Path = ENCRYPTED_BUNDLE) -> None:
    encrypt_bundle(payload=bundle_from_materialized(), recipient=recipient, output=output)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    dec = sub.add_parser("decrypt-materialize")
    dec.add_argument("--identity-file", type=Path, required=True)
    dec.add_argument("--encrypted", type=Path, default=ENCRYPTED_BUNDLE)
    enc = sub.add_parser("reencrypt-materialized")
    enc.add_argument("--recipient", required=True)
    enc.add_argument("--output", type=Path, default=ENCRYPTED_BUNDLE)
    args = parser.parse_args()
    if args.command == "decrypt-materialize":
        decrypt_and_materialize(encrypted=args.encrypted, identity_file=args.identity_file)
    else:
        reencrypt_materialized(recipient=args.recipient, output=args.output)


if __name__ == "__main__":
    main()
