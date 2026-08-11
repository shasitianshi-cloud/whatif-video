#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "INDEX.md"


def verify() -> bool:
    text = INDEX.read_text(encoding="utf-8")
    paths = re.findall(r"`([^`]+)`", text)
    static = [p for p in paths if p.startswith(("src/", "prompts/", "config/", "tests/"))]
    missing = [p for p in static if not (ROOT / p).exists()]
    if missing:
        raise AssertionError(f"missing indexed paths: {missing}")
    return True


if __name__ == "__main__":
    verify()
    print("INDEX_CONSISTENT=true")
