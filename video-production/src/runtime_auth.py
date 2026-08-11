"""Project-local runtime auth persistence. Never log secret values."""
from __future__ import annotations

import json
import os
import stat
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_AUTH_ROOT = PROJECT_ROOT / ".runtime-auth"
VOLCENGINE_DIR = RUNTIME_AUTH_ROOT / "volcengine"
HAPPYHORSE_DIR = RUNTIME_AUTH_ROOT / "happyhorse"
VOLCENGINE_CREDENTIAL = VOLCENGINE_DIR / "credential.json"
HAPPYHORSE_SESSION = HAPPYHORSE_DIR / "session.json"


def _chmod(path: Path, mode: int) -> None:
    path.chmod(mode)


def ensure_runtime_auth_root() -> None:
    for path in (RUNTIME_AUTH_ROOT, VOLCENGINE_DIR, HAPPYHORSE_DIR):
        path.mkdir(parents=True, exist_ok=True)
        _chmod(path, 0o700)


def _atomic_secret_json(path: Path, payload: dict) -> None:
    ensure_runtime_auth_root()
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _chmod(tmp, 0o600)
        os.replace(tmp, path)
        _chmod(path, 0o600)
    finally:
        tmp.unlink(missing_ok=True)


def persist_volcengine_from_environment() -> bool:
    value = os.environ.get("VOLCENGINE_TTS_API_KEY", "").strip()
    if not value:
        return False
    _atomic_secret_json(VOLCENGINE_CREDENTIAL, {"api_key": value})
    return True


def resolve_volcengine_api_key() -> tuple[str | None, str]:
    value = os.environ.get("VOLCENGINE_TTS_API_KEY", "").strip()
    if value:
        return value, "environment"
    if VOLCENGINE_CREDENTIAL.is_file():
        payload = json.loads(VOLCENGINE_CREDENTIAL.read_text(encoding="utf-8"))
        value = str(payload.get("api_key", "")).strip()
        if value:
            return value, "project_local_runtime_auth"
    return None, "unavailable"


def persist_happyhorse_session_from_path(source: Path) -> bool:
    if not source.is_file():
        return False
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("HappyHorse session must be a JSON object")
    _atomic_secret_json(HAPPYHORSE_SESSION, payload)
    return True


def load_happyhorse_session() -> dict | None:
    if not HAPPYHORSE_SESSION.is_file():
        return None
    payload = json.loads(HAPPYHORSE_SESSION.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def happyhorse_session_state(session: dict | None) -> dict:
    if not session:
        return {"present": False, "valid": False, "refresh_supported": False, "expiry_state": "missing"}
    access = session.get("accessToken") or session.get("access_token")
    refresh = session.get("refreshToken") or session.get("refresh_token")
    access_expiry = session.get("accessExpiresAt") or session.get("access_expires_at") or session.get("accessExpiryMs")
    now_ms = int(time.time() * 1000)
    expiry_state = "unknown"
    if isinstance(access_expiry, (int, float)):
        expiry_state = "expired" if int(access_expiry) <= now_ms else "valid"
    valid = bool(access) and expiry_state != "expired"
    return {
        "present": bool(access or refresh),
        "valid": valid,
        "refresh_supported": bool(refresh),
        "expiry_state": expiry_state,
    }


def permissions_metadata() -> dict:
    def mode(path: Path) -> str | None:
        if not path.exists():
            return None
        return oct(stat.S_IMODE(path.stat().st_mode))
    return {
        "runtime_auth_root": RUNTIME_AUTH_ROOT.as_posix(),
        "runtime_auth_dir_permission": mode(RUNTIME_AUTH_ROOT),
        "volcengine_secret_permission": mode(VOLCENGINE_CREDENTIAL),
        "happyhorse_secret_permission": mode(HAPPYHORSE_SESSION),
    }
