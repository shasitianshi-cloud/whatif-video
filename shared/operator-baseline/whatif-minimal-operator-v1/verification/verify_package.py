#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_package.py — whatif-minimal-operator-v1 包完整性与功能复核。

这不是治理系统，也不是测试框架。它只做 9 件事：

  1. 必要文件存在
  2. src/relation_operator.py 的 SHA256 与 manifest 一致
  3. 最小冻结源引用的 SHA256 与 manifest 记录一致（原件可访问时同时校验原件）
  4. SHA256SUMS.txt 可复算
  5. 运算子可被加载
  6. 不在冻结源生成 .pyc
  7. smoke test 可运行
  8. Evidence 可产生
  9. 没有知识写回（包内与冻结源在 smoke 前后逐字节不变）

smoke test 的 Evidence 写入**临时目录**，不污染包内已验收 Evidence。

用法：
    python verification/verify_package.py [-v]

冻结源根目录解析优先级：
    KR_FROZEN_SOURCE_ROOT 环境变量
    <pkg>/../knowledge-runtime-prototype
    <pkg>/../../knowledge-runtime-prototype
    <pkg>/frozen-source-reference          （包内只读参考副本）
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PKG = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
VERBOSE = "-v" in sys.argv or "--verbose" in sys.argv

REQUIRED = [
    "src/relation_operator.py",
    "tests/test-input.human.json",
    "evidence/operator-calls.jsonl",
    "verification/verify_package.py",
    "docs/README.md",
    "docs/SOURCE_INSPECTION.md",
    "docs/CAPABILITY_BOUNDARY.md",
    "docs/DEPENDENCY_CLOSURE.md",
    "frozen-source-reference/NOTICE.txt",
    "manifest.json",
    "SHA256SUMS.txt",
]

FROZEN_DEPS = [
    "audit/relation_audit.py",
    "ontology-core/typed-relations.schema.json",
    "ontology-core/shared-envelope.schema.json",
]

FAILURES: list[str] = []


def fail(msg):
    FAILURES.append(msg)
    print(f"  FAIL  {msg}")


def ok(msg):
    if VERBOSE:
        print(f"  ok    {msg}")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_sha(path):
    """JSON 语义摘要：忽略换行符、缩进和对象键顺序等文本表示差异。"""
    with open(path, "r", encoding="utf-8") as fh:
        obj = json.load(fh)
    data = json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def snapshot(root):
    """整棵树的 {相对路径: sha256}，用于证明没有任何写回。"""
    out = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            p = os.path.join(base, fn)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = sha(p)
    return out


def count_pyc(root):
    n = 0
    for base, _dirs, files in os.walk(root):
        if os.path.basename(base) == "__pycache__":
            n += len(files)
        n += sum(1 for f in files if f.endswith(".pyc"))
    return n


def resolve_frozen_root():
    env = os.environ.get("KR_FROZEN_SOURCE_ROOT")
    cands = []
    if env:
        cands.append((env, "ENV"))
    parent = os.path.dirname(PKG)
    cands.append((os.path.join(parent, "knowledge-runtime-prototype"), "ORIGINAL"))
    cands.append((os.path.join(os.path.dirname(parent), "knowledge-runtime-prototype"), "ORIGINAL"))
    cands.append((os.path.join(PKG, "frozen-source-reference"), "REFERENCE_COPY"))
    for path, mode in cands:
        if all(os.path.isfile(os.path.join(path, *d.split("/"))) for d in FROZEN_DEPS):
            return os.path.abspath(path), mode
    return None, "UNRESOLVED"


# ---------------------------------------------------------------- 1. 必要文件

print("[1] required files")
for rel in REQUIRED:
    p = os.path.join(PKG, *rel.split("/"))
    if os.path.isfile(p):
        ok(rel)
    else:
        fail(f"MISSING_FILE: {rel}")
for rel in FROZEN_DEPS:
    p = os.path.join(PKG, "frozen-source-reference", *rel.split("/"))
    if os.path.isfile(p):
        ok(f"frozen-source-reference/{rel}")
    else:
        fail(f"MISSING_FILE: frozen-source-reference/{rel}")

manifest_path = os.path.join(PKG, "manifest.json")
manifest = {}
if os.path.isfile(manifest_path):
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
else:
    fail("MANIFEST_UNREADABLE")

# ---------------------------------------------------------------- 2/3. manifest SHA256

print("[2] manifest file hashes")
for rel, expected in sorted((manifest.get("files") or {}).items()):
    p = os.path.join(PKG, *rel.split("/"))
    if not os.path.isfile(p):
        fail(f"MANIFEST_FILE_MISSING: {rel}")
        continue
    actual = sha(p)
    if actual != expected:
        fail(f"MANIFEST_SHA_MISMATCH: {rel}\n          expected {expected}\n          actual   {actual}")
    else:
        ok(f"{rel}  {actual[:16]}…")

print("[3] frozen source dependency hashes")
frozen_root, frozen_mode = resolve_frozen_root()
print(f"  FROZEN_SOURCE_ROOT = {frozen_root}  ({frozen_mode})")
fsd = manifest.get("frozen_source_dependencies") or {}
for rel in FROZEN_DEPS:
    expected = (fsd.get("files") or {}).get(rel)
    if not expected:
        fail(f"MANIFEST_MISSING_FROZEN_DEP: {rel}")
        continue
    # 包内参考副本
    ref = os.path.join(PKG, "frozen-source-reference", *rel.split("/"))
    if os.path.isfile(ref):
        a = sha(ref)
        if a != expected:
            fail(f"REFERENCE_COPY_SHA_MISMATCH: {rel}")
        else:
            ok(f"reference copy  {rel}")
    # 冻结源原件（可访问时）
    if frozen_root and frozen_mode != "REFERENCE_COPY":
        live = os.path.join(frozen_root, *rel.split("/"))
        if os.path.isfile(live):
            a = sha(live)
            if a != expected:
                fail(f"FROZEN_SOURCE_SHA_MISMATCH: {rel}")
            else:
                ok(f"frozen original {rel}")

# ---------------------------------------------------------------- 4. SHA256SUMS

print("[4] SHA256SUMS.txt recompute")
sums_path = os.path.join(PKG, "SHA256SUMS.txt")
listed = 0
if os.path.isfile(sums_path):
    with open(sums_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            digest, _sep, rel = line.partition("  ")
            rel = rel.strip()
            p = os.path.join(PKG, *rel.split("/"))
            listed += 1
            if not os.path.isfile(p):
                fail(f"SUMS_FILE_MISSING: {rel}")
            elif sha(p) != digest:
                fail(f"SUMS_SHA_MISMATCH: {rel}")
    print(f"  entries checked = {listed}")
else:
    fail("SHA256SUMS_MISSING")

PACKAGE_INTEGRITY = not FAILURES

# ---------------------------------------------------------------- 5/6. 加载

print("[5] operator load")
pre_pkg = snapshot(PKG)
pre_frozen = snapshot(frozen_root) if frozen_root else {}
pyc_before = count_pyc(frozen_root) if frozen_root else 0

OPERATOR_LOADABLE = False
ro = None
if frozen_root:
    os.environ["KR_FROZEN_SOURCE_ROOT"] = frozen_root
try:
    spec = importlib.util.spec_from_file_location(
        "whatif_relation_operator", os.path.join(PKG, "src", "relation_operator.py"))
    ro = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ro)
    if frozen_root:
        ro.FROZEN_SOURCE_ROOT = frozen_root
    idx, enum = ro._registry()
    OPERATOR_LOADABLE = callable(ro.operate) and len(enum) > 0
    print(f"  entrypoint operate(...) : {'present' if callable(ro.operate) else 'MISSING'}")
    print(f"  controlled relations    : {len(enum)}")
    print(f"  projected functions     : {len(ro.PROJECTED_FUNCTIONS)}")
except Exception as exc:  # noqa: BLE001
    fail(f"OPERATOR_LOAD_ERROR: {type(exc).__name__}: {exc}")

pyc_after = count_pyc(frozen_root) if frozen_root else 0
print(f"[6] pyc in frozen source: before={pyc_before} after={pyc_after}")
if pyc_after != 0:
    fail(f"PYC_WRITTEN_TO_FROZEN_SOURCE: {pyc_after}")

# ---------------------------------------------------------------- 7/8. smoke test

print("[7] smoke test (evidence -> temp dir)")
SMOKE_TEST_PASS = False
tmp = tempfile.mkdtemp(prefix="wmo-verify-")
try:
    if ro is not None:
        with open(os.path.join(PKG, "tests", "test-input.human.json"), "r", encoding="utf-8") as fh:
            specin = json.load(fh)
        run_id = "verify-package-run"
        trace = ro.EvidenceTrace(os.path.join(tmp, "evidence"), run_id)
        nodes, edges = specin["nodes"], specin["edges"]
        r1 = ro.operate("expand", {"seed": specin["anchor"], "nodes": nodes,
                                   "edges": edges, "max_depth": 1}, trace)
        r2 = ro.operate("perturb", {"nodes": nodes, "edges": edges,
                                    "perturbation": specin["perturbation"]}, trace)
        r3 = ro.operate("propagate", {"seed": specin["propagate_seed"], "nodes": nodes,
                                      "edges": r2["result"]["edges_after"],
                                      "max_depth": int(specin.get("max_depth", 4))}, trace)
        for tag, r in (("expand", r1), ("perturb", r2), ("propagate", r3)):
            print(f"  {tag:<10} decision={r['decision']} seq={r.get('evidence_seq')}")

        # 8. Evidence 可产生
        tracefile = os.path.join(tmp, "evidence", "operator-calls.jsonl")
        lines = []
        if os.path.isfile(tracefile):
            with open(tracefile, "r", encoding="utf-8") as fh:
                lines = [json.loads(x) for x in fh if x.strip()]
        objs = os.path.join(tmp, "evidence", "objects", run_id)
        nobj = len(os.listdir(objs)) if os.path.isdir(objs) else 0
        print(f"[8] evidence: trace_lines={len(lines)} objects={nobj}")

        # 与包内已验收 Evidence 的结果对象做 JSON 语义比对。
        # 不比较原始文件字节，避免 Windows CRLF / Unix LF 等文本表示差异造成误判。
        identical = True
        for fn in ("001-expand-result.json", "002-perturb-result.json", "003-propagate-result.json"):
            a = os.path.join(objs, fn)
            b = os.path.join(PKG, "evidence", "objects",
                             manifest.get("smoke_test_run_id", ""), fn)
            if not (os.path.isfile(a) and os.path.isfile(b)):
                identical = False
                continue
            if canonical_json_sha(a) != canonical_json_sha(b):
                identical = False
        print(f"  stateless replay semantically identical to packaged evidence: {identical}")

        SMOKE_TEST_PASS = (
            r1["decision"] == "CONTINUE"
            and r2["decision"] == "CONTINUE"
            and r3["decision"] == "STOP"
            and len(lines) == 3
            and nobj == 6
            and identical
        )
        if not SMOKE_TEST_PASS:
            fail("SMOKE_TEST_UNEXPECTED_RESULT")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---------------------------------------------------------------- 9. 无写回

print("[9] no knowledge persistence")
post_pkg = snapshot(PKG)
post_frozen = snapshot(frozen_root) if frozen_root else {}

pkg_delta = sorted(set(post_pkg) ^ set(pre_pkg)) + \
    sorted(k for k in set(post_pkg) & set(pre_pkg) if post_pkg[k] != pre_pkg[k])
frozen_delta = sorted(set(post_frozen) ^ set(pre_frozen)) + \
    sorted(k for k in set(post_frozen) & set(pre_frozen) if post_frozen[k] != pre_frozen[k])

print(f"  package tree delta      : {len(pkg_delta)}")
print(f"  frozen source tree delta: {len(frozen_delta)}  (files={len(post_frozen)})")
if pkg_delta:
    fail(f"PACKAGE_MUTATED_BY_RUN: {pkg_delta[:5]}")
if frozen_delta:
    fail(f"FROZEN_SOURCE_MUTATED_BY_RUN: {frozen_delta[:5]}")

FROZEN_SOURCE_UNCHANGED = (not frozen_delta) and pyc_after == 0 and frozen_root is not None
KNOWLEDGE_PERSISTENCE = bool(pkg_delta or frozen_delta)
PACKAGE_INTEGRITY = PACKAGE_INTEGRITY and not FAILURES

# ---------------------------------------------------------------- 结果

print()
print(f"PACKAGE_INTEGRITY={str(PACKAGE_INTEGRITY).lower()}")
print(f"OPERATOR_LOADABLE={str(OPERATOR_LOADABLE).lower()}")
print(f"SMOKE_TEST_PASS={str(SMOKE_TEST_PASS).lower()}")
print(f"FROZEN_SOURCE_UNCHANGED={str(FROZEN_SOURCE_UNCHANGED).lower()}")
print(f"KNOWLEDGE_PERSISTENCE={str(KNOWLEDGE_PERSISTENCE).lower()}")

allpass = (PACKAGE_INTEGRITY and OPERATOR_LOADABLE and SMOKE_TEST_PASS
           and FROZEN_SOURCE_UNCHANGED and not KNOWLEDGE_PERSISTENCE)
if not allpass:
    print(f"\nFAILURES={len(FAILURES)}")
sys.exit(0 if allpass else 1)
