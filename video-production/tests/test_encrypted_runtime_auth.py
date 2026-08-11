from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import encrypted_runtime_auth as era
import runtime_auth as ra


def synthetic_bundle() -> dict:
    return {
        "schema_version": 1,
        "volcengine": {"api_key": "synthetic-not-a-real-secret"},
        "happyhorse": {
            "accessToken": "synthetic-access",
            "refreshToken": "synthetic-refresh",
            "accessExpiresAt": 4102444800000
        }
    }


def test_schema_and_materialization(tmp_path, monkeypatch):
    root = tmp_path / ".runtime-auth"
    volc = root / "volcengine" / "credential.json"
    hh = root / "happyhorse" / "session.json"
    monkeypatch.setattr(ra, "RUNTIME_AUTH_ROOT", root)
    monkeypatch.setattr(ra, "VOLCENGINE_DIR", volc.parent)
    monkeypatch.setattr(ra, "HAPPYHORSE_DIR", hh.parent)
    monkeypatch.setattr(ra, "VOLCENGINE_CREDENTIAL", volc)
    monkeypatch.setattr(ra, "HAPPYHORSE_SESSION", hh)
    monkeypatch.setattr(era, "VOLCENGINE_CREDENTIAL", volc)
    monkeypatch.setattr(era, "HAPPYHORSE_SESSION", hh)

    payload = synthetic_bundle()
    era.validate_bundle(payload)
    era.materialize_bundle(payload)
    assert json.loads(volc.read_text())["api_key"] == "synthetic-not-a-real-secret"
    assert json.loads(hh.read_text())["refreshToken"] == "synthetic-refresh"
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(volc.stat().st_mode) == 0o600
    assert stat.S_IMODE(hh.stat().st_mode) == 0o600


def test_invalid_bundle_fail_closed():
    bad = {"schema_version": 1, "volcengine": {}, "happyhorse": {}}
    try:
        era.validate_bundle(bad)
    except RuntimeError:
        return
    raise AssertionError("invalid bundle must fail closed")
