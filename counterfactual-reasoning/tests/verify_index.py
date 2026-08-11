#!/usr/bin/env python3
from pathlib import Path
import re
import sys

module = Path(__file__).resolve().parents[1]
project = module.parent
text = (module / "INDEX.md").read_text(encoding="utf-8")
paths = re.findall(r"`([^`]+(?:\.py|\.md|\.json|\.zip))`", text)
missing = []
for item in paths:
    if "<run_id>" in item or item in {"counterfactual-master.md", "evidence/semantic-continue-block.json"}:
        continue
    target = (module / item).resolve()
    if not target.exists():
        missing.append(item)
if missing:
    print("INDEX_CONSISTENT=false")
    print("MISSING=" + ",".join(missing))
    sys.exit(1)
print("INDEX_CONSISTENT=true")
