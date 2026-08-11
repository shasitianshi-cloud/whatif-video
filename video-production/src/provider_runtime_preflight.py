"""Deterministic, no-generation provider runtime auth preflight."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from runtime_auth import (
    HAPPYHORSE_SESSION,
    RUNTIME_AUTH_ROOT,
    happyhorse_session_state,
    load_happyhorse_session,
    permissions_metadata,
    persist_happyhorse_session_from_path,
    persist_volcengine_from_environment,
    resolve_volcengine_api_key,
)


def run_preflight(*, persist_env: bool = False, happyhorse_session_source: Path | None = None) -> dict:
    if persist_env:
        persist_volcengine_from_environment()
    if happyhorse_session_source is not None:
        persist_happyhorse_session_from_path(happyhorse_session_source)

    api_key, tts_source = resolve_volcengine_api_key()
    hh_state = happyhorse_session_state(load_happyhorse_session())
    perms = permissions_metadata()
    ready = bool(api_key) and hh_state["present"] and (hh_state["valid"] or hh_state["refresh_supported"])
    return {
        "provider_runtime_preflight": "PASS" if ready else "BLOCKED",
        "provider_runtime_preflight_ready": ready,
        "volcengine_tts_credential_present": bool(api_key),
        "volcengine_tts_credential_source": tts_source,
        "happyhorse_session_present": hh_state["present"],
        "happyhorse_session_valid": hh_state["valid"],
        "happyhorse_refresh_supported": hh_state["refresh_supported"],
        "happyhorse_expiry_state": hh_state["expiry_state"],
        "happyhorse_session_source": "project_local_runtime_auth" if HAPPYHORSE_SESSION.is_file() else "unavailable",
        "builtin_image_secret_required": False,
        "hyperframes_secret_required": False,
        "runtime_auth_root": RUNTIME_AUTH_ROOT.as_posix(),
        **perms,
        "run_id_created": False,
        "provider_generation_call_executed": False,
        "credits_consumed": False,
        "secret_value_exposed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--persist-current-env", action="store_true")
    parser.add_argument("--happyhorse-session-source", type=Path)
    parser.add_argument("--encrypted-auth", type=Path)
    parser.add_argument("--age-identity-file", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()

    encrypted_loaded = False
    if args.encrypted_auth or args.age_identity_file:
        if not args.encrypted_auth or not args.age_identity_file:
            raise SystemExit("--encrypted-auth and --age-identity-file must be supplied together")
        from encrypted_runtime_auth import decrypt_and_materialize
        decrypt_and_materialize(encrypted=args.encrypted_auth, identity_file=args.age_identity_file)
        encrypted_loaded = True

    result = run_preflight(
        persist_env=args.persist_current_env,
        happyhorse_session_source=args.happyhorse_session_source,
    )
    result["encrypted_runtime_auth_loaded"] = encrypted_loaded
    result["encrypted_runtime_auth_transport"] = "age" if encrypted_loaded else "not_used"
    if args.result:
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["provider_runtime_preflight_ready"] else 3)


if __name__ == "__main__":
    main()
