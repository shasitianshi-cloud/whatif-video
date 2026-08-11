#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WHATIF_MINIMAL_OPERATOR_PROJECTION_V1
=====================================
What-if 项目侧【最小、无状态、可观察】关系运算子。

这不是动力知识系统的副本，也不是它的运行时。
它只投影 What-if 关系运算真正需要的那一小块能力：

  从冻结动力池 READ-ONLY 复用（函数级，不复制实现）：
    audit/relation_audit.py ::
        registry_index          关系元数据权威索引（20 受控关系 + 元数据）
        resolve_roles           record_type -> 语义角色（唯一 canonical 角色映射）
        endpoint_ok             端点角色合法性（多角色感知 / 未知 fail-closed）
        reciprocity_violations  反向边违例检测（用于 reverse_edge 扰动裁决）
        transitive_inference    语义传递闭包（推断视图，不写回）
    ontology-core/typed-relations.schema.json    （由上述函数读取）
    ontology-core/shared-envelope.schema.json    （由上述函数读取）

  明确不带入：
    archetype schema 层 / composition / routing / projections / runtime-records /
    domain-connector / external-contract / validate_prototype / 全部治理文档。

对冻结源只有 open("r")。本模块设置 sys.dont_write_bytecode，
保证 import 冻结源代码时不会在冻结目录里生成 __pycache__。

性质：
  Stateless             一次调用 input -> computation -> output，无跨调用知识状态
  No Persistence        不写知识、不更新本体、不产生 runtime-record
  Explicit Input        不自动寻找 anchor / 上次 run / 上次 premise，run_id 必须显式给
  Observable            旁路 append-only trace：evidence/operator-calls.jsonl

对外只有一个入口：

    operate(intent, payload, trace=None) -> dict

intent ∈ {"expand", "perturb", "propagate"}
  expand / propagate 共用同一个 _walk 核心（能力合并，不拆成两个运算子）；
  状态变化 / 关系接管 / 终态 作为 _walk 的输出字段，不单独做 State Engine；
  CONTINUE / STOP / INVALID 由布尔逻辑给出，不引入评分体系。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from functools import lru_cache

# 关键：import 冻结源代码时不得在冻结目录写入 .pyc
sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

# ---------------------------------------------------------------- 冻结源（只读）

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_FROZEN = os.path.join(os.path.dirname(_HERE), "knowledge-runtime-prototype")
FROZEN_SOURCE_ROOT = os.environ.get("KR_FROZEN_SOURCE_ROOT", _DEFAULT_FROZEN)

# 依赖闭包：从冻结源投影的全部函数，仅此 5 个
PROJECTED_FUNCTIONS = (
    "registry_index",
    "resolve_roles",
    "endpoint_ok",
    "reciprocity_violations",
    "transitive_inference",
)


class OperatorError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _frozen():
    """静态引用冻结源实现（不动态发现、不复制）。
    lru_cache 只缓存不可变的冻结内容，不构成跨调用知识状态。"""
    path = os.path.join(FROZEN_SOURCE_ROOT, "audit", "relation_audit.py")
    if not os.path.isfile(path):
        raise OperatorError(f"FROZEN_SOURCE_NOT_FOUND: {path}")
    spec = importlib.util.spec_from_file_location("kr_relation_audit_ro", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    missing = [n for n in PROJECTED_FUNCTIONS if not hasattr(mod, n)]
    if missing:
        raise OperatorError(f"FROZEN_SOURCE_CAPABILITY_MISSING: {missing}")
    return {n: getattr(mod, n) for n in PROJECTED_FUNCTIONS}


@lru_cache(maxsize=1)
def _registry():
    idx, enum = _frozen()["registry_index"]()
    return idx, enum


# ---------------------------------------------------------------- 基元


def _triple(e):
    return (e["source"], e["relation"], e["target"])


def _nodes_index(payload):
    nodes = {}
    for n in payload.get("nodes", []):
        unit = {"record_type": n.get("record_type")}
        if n.get("archetype_role"):
            unit["archetype_role"] = n["archetype_role"]
        nodes[n["id"]] = unit
    return nodes


def _roles(node_id, nodes):
    unit = nodes.get(node_id)
    if unit is None:
        return set()
    return _frozen()["resolve_roles"](unit)


def _partition_edges(edges, nodes):
    """用冻结源的 endpoint_ok 把调用方给的边分成 legal / rejected。
    未声明节点、未知 record_type、受控词表外关系一律 fail-closed。"""
    idx, enum = _registry()
    endpoint_ok = _frozen()["endpoint_ok"]
    legal, rejected = [], []
    for e in edges:
        s, rel, t = _triple(e)
        if rel not in enum:
            rejected.append({**e, "reject_reason": "RELATION_NOT_IN_CONTROLLED_VOCABULARY"})
            continue
        if s not in nodes or t not in nodes:
            rejected.append({**e, "reject_reason": "ENDPOINT_NODE_NOT_DECLARED"})
            continue
        ok, sr, tr = endpoint_ok(rel, nodes[s], nodes[t], idx)
        if not ok:
            rejected.append({
                **e,
                "reject_reason": "ENDPOINT_ROLE_REJECTED",
                "source_roles": sorted(sr),
                "target_roles": sorted(tr),
                "allowed_source_roles": sorted(idx[rel]["source_role"]),
                "allowed_target_roles": sorted(idx[rel]["target_role"]),
            })
            continue
        legal.append({"source": s, "relation": rel, "target": t})
    return legal, rejected


def _adjacency(legal_edges):
    """有向邻接；registry.direction == bidirectional 的关系同时可反向游走。"""
    idx, _ = _registry()
    adj = {}
    for e in legal_edges:
        s, rel, t = _triple(e)
        adj.setdefault(s, []).append((rel, t))
        if idx[rel]["direction"] == "bidirectional":
            adj.setdefault(t, []).append((rel, s))
    return adj


def _derived_view(legal_edges):
    """复用冻结源 transitive_inference：对显式图上出现过的关系逐个求语义传递闭包。
    结果只是推断视图（storage_policy = store_explicit_edges_only，不写回、不参与游走）。"""
    idx, _ = _registry()
    ti = _frozen()["transitive_inference"]
    out = []
    for rel in sorted({e["relation"] for e in legal_edges}):
        if idx[rel]["semantic_transitivity"] == "non_transitive":
            continue
        for (s, t) in sorted(ti(rel, [_triple(e) for e in legal_edges], idx=idx)):
            out.append({"source": s, "relation": rel, "target": t, "origin": "inferred"})
    return out


# ---------------------------------------------------------------- 核心：关系游走
# expand 与 propagate 共用；状态变化 / 关系接管 / 终态 折叠在这里，不做独立 State Engine。


def _walk(payload, intent):
    seed = payload.get("seed")
    nodes = _nodes_index(payload)
    edges = payload.get("edges", [])
    only = set(payload.get("relations") or [])
    max_depth = int(payload.get("max_depth", 1))

    invalid = []
    if not seed:
        invalid.append("SEED_NOT_PROVIDED")
    elif seed not in nodes:
        invalid.append("SEED_NODE_NOT_DECLARED")
    elif not _roles(seed, nodes):
        invalid.append("SEED_ROLE_UNRESOLVED")
    _, enum = _registry()
    for r in only:
        if r not in enum:
            invalid.append(f"REQUESTED_RELATION_NOT_CONTROLLED:{r}")

    legal, rejected = _partition_edges(edges, nodes)
    adj = _adjacency(legal)

    layers = []
    visited = {seed} if seed else set()
    frontier = [seed] if seed else []
    seen_rels, seen_roles = set(), set(_roles(seed, nodes)) if seed else set()

    if not invalid:
        for depth in range(1, max_depth + 1):
            steps, new_nodes = [], []
            used_rels, used_roles = set(), set()
            for n in frontier:
                for rel, t in adj.get(n, []):
                    if only and rel not in only:
                        continue
                    is_new = t not in visited and t not in new_nodes
                    steps.append({"from": n, "relation": rel, "to": t, "new_node": is_new})
                    used_rels.add(rel)
                    used_roles |= _roles(t, nodes)
                    if is_new:
                        new_nodes.append(t)
            new_rels = sorted(used_rels - seen_rels)
            new_roles = sorted(used_roles - seen_roles)
            layers.append({
                "depth": depth,
                "steps": steps,
                "new_nodes": new_nodes,
                "relation_types": sorted(used_rels),
                "newly_dominant_relations": new_rels,
                "newly_entered_roles": new_roles,
                # 关系接管：更深一层出现了上一层没有用过的关系类型或语义角色
                "regime_change": bool(depth > 1 and (new_rels or new_roles)),
            })
            visited.update(new_nodes)
            seen_rels |= used_rels
            seen_roles |= used_roles
            frontier = new_nodes
            if not frontier:
                break

    # 终态：已到达且没有任何合法出边的节点
    terminal = sorted(n for n in visited if not adj.get(n))
    frontier_remaining = bool(frontier)

    if invalid:
        decision = "invalid"
    elif frontier_remaining:
        decision = "continue"      # 还有未展开的关系可能改变结果
    else:
        decision = "stop"          # 关系已闭合，再走只会重复同类后果

    return {
        "seed": seed,
        "max_depth": max_depth,
        "edges_legal": legal,
        "edges_rejected": rejected,
        "layers": layers,
        "reached_nodes": sorted(visited),
        "terminal_nodes": terminal,
        "regime_change_depths": [l["depth"] for l in layers if l["regime_change"]],
        "frontier_remaining": frontier_remaining,
        "derived_view": _derived_view(legal) if intent == "expand" else [],
        "decision": decision,
        "invalid_reasons": invalid,
    }


# ---------------------------------------------------------------- 核心：关系扰动
# 冻结池的知识模型只有「节点 + 受控类型化边」，没有数值属性层。
# 因此题面列举的属性/数量/比例/尺度/速度/持续时间/状态/同步 改变全部塌缩为 set_attribute；
# 关系断开 / 约束移除 = remove_edge；关系反转 = reverse_edge。共 3 种结构算子，不另建 Intervention Framework。


_PERTURBATIONS = ("remove_edge", "reverse_edge", "set_attribute")


def _perturb(payload):
    nodes = _nodes_index(payload)
    edges = [dict(e) for e in payload.get("edges", [])]
    p = payload.get("perturbation") or {}
    kind = p.get("kind")

    invalid, notices, removed, added = [], [], [], []

    if kind not in _PERTURBATIONS:
        invalid.append(f"PERTURBATION_KIND_UNSUPPORTED:{kind}")
        return {"perturbation": p, "edges_after": edges, "removed": [], "added": [],
                "notices": notices, "decision": "invalid", "invalid_reasons": invalid}

    idx, enum = _registry()

    if kind in ("remove_edge", "reverse_edge"):
        tgt = p.get("edge") or {}
        key = (tgt.get("source"), tgt.get("relation"), tgt.get("target"))
        if key[1] not in enum:
            invalid.append(f"RELATION_NOT_IN_CONTROLLED_VOCABULARY:{key[1]}")
        match = [e for e in edges if _triple(e) == key]
        if not match:
            invalid.append("PERTURBATION_TARGET_EDGE_NOT_FOUND")
        if not invalid:
            edges = [e for e in edges if _triple(e) != key]
            removed.append({"source": key[0], "relation": key[1], "target": key[2]})
            if kind == "reverse_edge":
                recip = idx[key[1]]["reciprocity"]
                if recip == "symmetric":
                    edges.append(match[0])
                    removed.pop()
                    notices.append(f"NO_OP_SYMMETRIC_RELATION:{key[1]} 已是对称关系，反转不改变图")
                else:
                    rev = {"source": key[2], "relation": key[1], "target": key[0]}
                    edges.append(rev)
                    added.append(rev)
                    if recip == "anti_reciprocal":
                        notices.append(
                            f"ANTI_RECIPROCAL_REVERSAL:{key[1]} 为 anti_reciprocal，"
                            "反转后的边在现实语义下与原边不可共存")
                    # 复用冻结源违例检测，确认反转没有制造 A R B ∧ B R A
                    viol = _frozen()["reciprocity_violations"]([_triple(e) for e in edges], idx)
                    if viol:
                        notices.append(f"RECIPROCITY_VIOLATION_INTRODUCED:{viol}")

    elif kind == "set_attribute":
        node_id = p.get("node")
        if node_id not in nodes:
            invalid.append("PERTURBATION_TARGET_NODE_NOT_DECLARED")
        elif not p.get("attribute"):
            invalid.append("PERTURBATION_ATTRIBUTE_NOT_PROVIDED")
        else:
            # 只在本次调用的返回值里表达，不写回任何节点存储
            notices.append(
                f"ATTRIBUTE_DELTA:{node_id}.{p['attribute']} = {p.get('value')!r}"
                f" ({p.get('mode', 'unspecified')})")

    return {
        "perturbation": p,
        "edges_after": edges,
        "removed": removed,
        "added": added,
        "notices": notices,
        "decision": "invalid" if invalid else "continue",
        "invalid_reasons": invalid,
    }


# ---------------------------------------------------------------- Evidence（旁路，append-only）


class EvidenceTrace:
    """极简旁路 trace。不被任何运算子读取，只写不读 —— 保证 Evidence 不是继续运行的输入。"""

    def __init__(self, directory, run_id):
        if not run_id:
            raise OperatorError("RUN_ID_REQUIRED: 运算子不负责 run 生命周期，run_id 必须由调用方显式提供")
        directory = os.path.abspath(directory)
        frozen = os.path.abspath(FROZEN_SOURCE_ROOT)
        if directory == frozen or directory.startswith(frozen + os.sep):
            raise OperatorError("EVIDENCE_DIR_INSIDE_FROZEN_SOURCE: 禁止向冻结源写入任何内容")
        self.run_id = run_id
        self.dir = directory
        self.objects = os.path.join(directory, "objects", run_id)
        os.makedirs(self.objects, exist_ok=True)
        self.trace_path = os.path.join(directory, "operator-calls.jsonl")
        self._seq = 0  # 进程内计数，从不回读 trace 文件

    def _dump(self, name, obj):
        path = os.path.join(self.objects, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
        return os.path.relpath(path, self.dir).replace(os.sep, "/")

    def record(self, operation, payload, result, decision, summary):
        self._seq += 1
        seq = self._seq
        in_ref = self._dump(f"{seq:03d}-{operation}-input.json", payload)
        out_ref = self._dump(f"{seq:03d}-{operation}-result.json", result)
        line = {
            "run_id": self.run_id,
            "seq": seq,
            "operation": operation,
            "input_ref": in_ref,
            "result_ref": out_ref,
            "decision": decision,
            "summary": summary,
        }
        with open(self.trace_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        return seq


# ---------------------------------------------------------------- 唯一入口


_INTENTS = ("expand", "perturb", "propagate")


def _summary(intent, result):
    if intent == "perturb":
        return (f"removed={len(result['removed'])} added={len(result['added'])} "
                f"notices={len(result['notices'])}")
    return (f"reached={len(result['reached_nodes'])} "
            f"rejected_edges={len(result['edges_rejected'])} "
            f"regime_change_at={result['regime_change_depths']} "
            f"terminal={result['terminal_nodes']}")


def operate(intent, payload, trace=None):
    """input + operation intent -> result + evidence。无状态；不读取任何历史。"""
    if intent not in _INTENTS:
        raise OperatorError(f"UNKNOWN_INTENT:{intent} (supported={_INTENTS})")
    result = _perturb(payload) if intent == "perturb" else _walk(payload, intent)
    envelope = {
        "projection": "WHATIF_MINIMAL_OPERATOR_PROJECTION_V1",
        "intent": intent,
        "decision": result["decision"].upper(),
        "invalid_reasons": result["invalid_reasons"],
        "result": result,
    }
    if trace is not None:
        envelope["evidence_seq"] = trace.record(
            intent, payload, result, result["decision"], _summary(intent, result))
    return envelope


# ---------------------------------------------------------------- 最小验证驱动（非模块能力）


def _cli():
    ap = argparse.ArgumentParser(description="Minimal Operator Projection — single functional run")
    ap.add_argument("--input", required=True, help="显式输入 JSON 路径")
    ap.add_argument("--run-id", required=True, help="调用方提供的 run_id（运算子不自动生成）")
    ap.add_argument("--evidence-dir", default=os.path.join(_HERE, "evidence"))
    a = ap.parse_args()

    with open(a.input, "r", encoding="utf-8") as fh:
        spec = json.load(fh)

    trace = EvidenceTrace(a.evidence_dir, a.run_id)
    nodes, edges = spec["nodes"], spec["edges"]

    r1 = operate("expand", {
        "seed": spec["anchor"], "nodes": nodes, "edges": edges, "max_depth": 1}, trace)

    r2 = operate("perturb", {
        "nodes": nodes, "edges": edges, "perturbation": spec["perturbation"]}, trace)

    r3 = operate("propagate", {
        "seed": spec["propagate_seed"], "nodes": nodes,
        "edges": r2["result"]["edges_after"], "max_depth": int(spec.get("max_depth", 4))}, trace)

    print(f"FROZEN_SOURCE_ROOT      : {FROZEN_SOURCE_ROOT}")
    print(f"PROJECTED_FUNCTIONS     : {', '.join(PROJECTED_FUNCTIONS)}")
    print(f"RUN_ID                  : {a.run_id}")
    print(f"ANCHOR                  : {spec['anchor']}")
    print()
    for tag, r in (("expand", r1), ("perturb", r2), ("propagate", r3)):
        print(f"[{tag}] decision={r['decision']} seq={r.get('evidence_seq')} "
              f"{_summary(tag, r['result'])}")
    print()
    print("expand.rejected_edges    :")
    for e in r1["result"]["edges_rejected"]:
        print(f"  - {e['source']} {e['relation']} {e['target']}  <- {e['reject_reason']}")
    print("expand.derived_view      :")
    for e in r1["result"]["derived_view"]:
        print(f"  - {e['source']} {e['relation']} {e['target']} (inferred)")
    print("perturb.notices          :", r2["result"]["notices"] or "none")
    print("propagate.layers         :")
    for l in r3["result"]["layers"]:
        print(f"  depth {l['depth']}: rel={l['relation_types']} new={l['new_nodes']} "
              f"regime_change={l['regime_change']} newly_dominant={l['newly_dominant_relations']}")
    print()
    print(f"EVIDENCE_TRACE           : {trace.trace_path}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
