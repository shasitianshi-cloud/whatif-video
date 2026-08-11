#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal deterministic Relation Audit Gate
(CONSOLIDATED_RELATION_SEMANTIC_PATCH_V1 → V2 recheck → EXECUTION_CLOSURE_PATCH_V1)

这是 `audit/global-audit-rules.md §5` 的确定性机器实现，消费：
  - ontology-core/typed-relations.schema.json 的 relation_registry[]（关系元数据权威）
  - ontology-core/shared-envelope.schema.json 的 record_type_semantic_roles（端点角色权威，**唯一**）

本轮（EXECUTION_CLOSURE_PATCH_V1）修复 V2 recheck 的三个 Root Cause：

  RC-A ROLE_RESOLUTION_MODEL
    - 删除手写 ROLE_MAP 第二权威；角色映射唯一来自 shared-envelope 的
      record_type_semantic_roles（CANONICAL_ROLE_MAPPING_SINGLE_SOURCE）。
    - resolve_roles() 返回**角色集合**（多角色感知）：端点判定为
      actual_roles ∩ allowed_roles ≠ ∅，而非「主角色 ∈ allowed」。
    - 未知 record_type → 空集（fail-closed / UNRESOLVED），不再静默等同 Entity。
  RC-B RELATION_INFERENCE_ENGINE
    - transitive_inference() 消费 direction=bidirectional（对称关系 T2/T3 闭合）。
    - 单次调用返回语义传递闭包（多跳），不写回 canonical graph。
    - conditional（part_of/has_part）要求外部 guard_resolver 回调；无 guard → 不推断。
      不把 partonomy_kind 作为核心 canonical 字段（Guard Contract 由调用方提供）。
  RC-C META_MODEL_CONSUMPTION
    - relation_metadata_integrity() 确定性消费 inverse/opposite（验证对称与端点互换），
      仅用于元数据完整性校验，不自动物化逆边（AUTO_INVERSE_EDGE_MATERIALIZATION=false）。

设计约束：
  - 不修改任何边的结构；不在边上重复存储 source_role/target_role（避免可伪造重复状态）。
  - 仅标准库，无外部依赖。
  - 角色解析优先 canonical record_type_semantic_roles；
    单元可携带显式 archetype_role（测试/夹具 escape hatch，非 canonical envelope 字段）。
  - 运行时集成（生产调用链）不在本阶段 scope；本 Gate 当前由 regression 确定性导入。
"""

import json
import os
import sys
from datetime import datetime, timezone

ROOT = None
for d in [os.path.abspath(os.path.dirname(__file__)),
          os.path.abspath(os.path.dirname(os.path.dirname(__file__)))]:
    if os.path.isdir(os.path.join(d, "ontology-core")):
        ROOT = d
        break
if ROOT is None:
    ROOT = os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

SCHEMA_PATH = os.path.join(ROOT, "ontology-core", "typed-relations.schema.json")
SHARED_ENV_PATH = os.path.join(ROOT, "ontology-core", "shared-envelope.schema.json")


def load_registry():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
        obj = json.load(fh)
    return obj


def registry_index():
    obj = load_registry()
    idx = {r["relation"]: r for r in obj["relation_registry"]}
    enum = set(obj["$defs"]["controlled_relation"]["enum"])
    return idx, enum


def load_role_map():
    """唯一 canonical 机器角色映射：record_type -> 语义角色 token 列表。
    来源：shared-envelope.schema.json 的 record_type_semantic_roles。
    忽略非 list 的辅助键（如 _comment）。"""
    with open(SHARED_ENV_PATH, "r", encoding="utf-8") as fh:
        env = json.load(fh)
    raw = env["record_type_semantic_roles"]
    return {k: v for k, v in raw.items() if isinstance(v, list)}


def resolve_roles(unit, role_map=None):
    """返回单元的语义角色集合（多角色感知）。未知 record_type → 空集（fail-closed）。"""
    if role_map is None:
        role_map = load_role_map()
    if isinstance(unit, dict):
        # 显式覆盖（测试/夹具 escape hatch，非 canonical envelope 字段）
        ov = unit.get("archetype_role")
        if ov:
            if isinstance(ov, list):
                return set(ov)
            return {ov}
        rt = unit.get("record_type")
        if rt in role_map:
            return set(role_map[rt])
    return set()  # UNRESOLVED_ROLE — fail closed（不得静默等同 Entity）


def endpoint_ok(relation, src_unit, tgt_unit, idx=None):
    """端点角色是否被 relation_registry[relation] 的 source_role/target_role 允许。
    多角色感知：actual_roles ∩ allowed_roles ≠ ∅。
    ANY 在 allowed 集合中匹配任何非空已解析角色；未知单元角色为空 → 即使 ANY 也 FAIL。"""
    if idx is None:
        idx, _ = registry_index()
    reg = idx.get(relation)
    if reg is None:
        return False, set(), set()
    src_roles = resolve_roles(src_unit)
    tgt_roles = resolve_roles(tgt_unit)
    src_allowed = set(reg["source_role"])
    tgt_allowed = set(reg["target_role"])
    # ANY 在 allowed 集合中 = 允许任何「已识别 canonical 角色」；未知单元角色为空 → 即使 ANY 也 FAIL
    src_pass = bool(src_roles) and ("ANY" in src_allowed or bool(src_roles & src_allowed))
    tgt_pass = bool(tgt_roles) and ("ANY" in tgt_allowed or bool(tgt_roles & tgt_allowed))
    return (src_pass and tgt_pass), src_roles, tgt_roles


def reciprocity_violations(edges, idx=None):
    """返回 anti_reciprocal 关系出现反向边（A R B 且 B R A）的违例列表。"""
    if idx is None:
        idx, _ = registry_index()
    present = set()
    violations = []
    seen_pairs = set()
    for e in edges:
        s, rel, t = _as_triple(e)
        present.add((s, rel, t))
    for (s, rel, t) in list(present):
        reg = idx.get(rel)
        if reg is None:
            continue
        if reg["reciprocity"] == "anti_reciprocal":
            if (t, rel, s) in present:
                key = frozenset([(s, rel, t), (t, rel, s)])
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    violations.append((rel, s, t))
    return violations


def cycle_violations(edges, idx=None):
    """
    逐关系做环检测，按 cycle_policy 分类：
      - acyclic_by_definition：检测到环 => 硬违例（violations）
      - domain_specific_audit_concern：检测到环 => 软关注项（concerns），不在此层硬 FAIL
      - cycle_allowed / symmetric_cycle_allowed：不检测
    返回 (violations, concerns)
    """
    if idx is None:
        idx, _ = registry_index()
    by_rel = {}
    for e in edges:
        s, rel, t = _as_triple(e)
        by_rel.setdefault(rel, []).append((s, t))

    violations = []
    concerns = []
    for rel, pairs in by_rel.items():
        reg = idx.get(rel)
        if reg is None:
            continue
        cp = reg["cycle_policy"]
        if cp not in ("acyclic_by_definition", "domain_specific_audit_concern"):
            continue
        adj = {}
        for s, t in pairs:
            adj.setdefault(s, []).append(t)
            if reg["direction"] == "bidirectional":
                adj.setdefault(t, []).append(s)
        # DFS 环检测
        visited, stack = set(), set()
        found = [False]

        def visit(n):
            if n in stack:
                found[0] = True
                return
            if n in visited:
                return
            visited.add(n)
            stack.add(n)
            for m in adj.get(n, []):
                visit(m)
            stack.discard(n)

        for n in list(adj.keys()):
            visit(n)
            if found[0]:
                break
        if found[0]:
            if cp == "acyclic_by_definition":
                violations.append(rel)
            else:
                concerns.append(rel)
    return violations, concerns


def _bidirectional_adj(relation, edges, idx):
    """构建有向邻接表；bidirectional 关系同时扩展反向边（推断视图，不写回）。"""
    reg = idx[relation]
    adj = {}
    for e in edges:
        s, rel, t = _as_triple(e)
        if rel != relation:
            continue
        adj.setdefault(s, set()).add(t)
        if reg["direction"] == "bidirectional":
            adj.setdefault(t, set()).add(s)
    return adj


def _reachable_closure(adj):
    """全可达传递闭包（多跳），固定点迭代。"""
    closure = {n: set(neighbors) for n, neighbors in adj.items()}
    changed = True
    while changed:
        changed = False
        for n in list(closure):
            for m in list(closure[n]):
                for p in list(closure.get(m, [])):
                    if p != n and p not in closure[n]:
                        closure[n].add(p)
                        changed = True
    return closure


def _guarded_reachable_closure(adj, relation, guard_resolver):
    """条件传递闭包：仅当 guard_resolver(relation, source, intermediate, target) == 'ALLOW'
    时才扩展。guard 定义于连续相邻对。"""
    closure = {n: set(neighbors) for n, neighbors in adj.items()}
    changed = True
    while changed:
        changed = False
        for n in list(closure):
            for m in list(closure[n]):
                for p in list(closure.get(m, [])):
                    if p == n or p in closure[n]:
                        continue
                    if guard_resolver(relation, n, m, p) == "ALLOW":
                        closure[n].add(p)
                        changed = True
    return closure


def transitive_inference(relation, edges, guard_resolver=None, idx=None):
    """
    基于 semantic_transitivity 派生推断边（不写回存储）。

    - semantic_transitivity=transitive（specializes/equivalent_to/requires/precedes/derived_from）：
      返回当前显式 graph 上的**全可达语义闭包**（含多跳），由单次调用给出。
    - semantic_transitivity=conditional（part_of/has_part）：要求 guard_resolver 回调；
      guard_resolver 为 None → 不推断（GUARD_UNRESOLVED），避免默认允许或无字段假设。
    - inference_policy=not_allowed → 空集合。

    推断边只存在于返回值（推断视图），storage_policy=store_explicit_edges_only 不变。
    """
    if idx is None:
        idx, _ = registry_index()
    reg = idx.get(relation)
    if reg is None:
        return set()
    if reg["semantic_transitivity"] not in ("transitive", "conditional"):
        return set()
    if reg["inference_policy"] == "not_allowed":
        return set()

    adj = _bidirectional_adj(relation, edges, idx)
    explicit = {(s, t) for s in adj for t in adj[s]}

    if reg["semantic_transitivity"] == "conditional":
        if guard_resolver is None:
            return set()  # GUARD_UNRESOLVED — 无 guard 不推断
        closure = _guarded_reachable_closure(adj, relation, guard_resolver)
    else:
        closure = _reachable_closure(adj)

    inferred = set()
    for s in closure:
        for t in closure[s]:
            if s != t and (s, t) not in explicit:
                inferred.add((s, t))
    return inferred


def relation_metadata_integrity(idx=None):
    """
    RC-C：确定性消费 inverse / opposite 元数据，验证引用完整性与对称性。
    仅用于元数据完整性校验（声明用途），不自动物化逆边。

    检查：
      - inverse 非 none/self ⇒ 目标关系存在、其 inverse 反向指回、端点角色方向互换兼容；
      - opposite 非 none ⇒ 目标关系存在、其 opposite 反向指回；
      - inverse=self ⇒ reciprocity=symmetric 且 direction=bidirectional（对称自逆一致）。
    返回 (ok, violations)。
    """
    if idx is None:
        idx, _ = registry_index()
    violations = []
    for name, reg in idx.items():
        inv = reg["inverse"]
        if inv not in ("none", "self"):
            if inv not in idx:
                violations.append(f"{name}.inverse={inv} 但目标关系不存在")
                continue
            q = idx[inv]
            if q["inverse"] != name:
                violations.append(
                    f"{name}.inverse={inv} 但 {inv}.inverse={q['inverse']} ≠ {name}")
            if (set(q["source_role"]) != set(reg["target_role"])
                    or set(q["target_role"]) != set(reg["source_role"])):
                violations.append(f"{name}↔{inv} 端点角色未方向互换兼容")
        opp = reg["opposite"]
        if opp != "none":
            if opp not in idx:
                violations.append(f"{name}.opposite={opp} 但目标关系不存在")
                continue
            if idx[opp]["opposite"] != name:
                violations.append(
                    f"{name}.opposite={opp} 但 {opp}.opposite={idx[opp]['opposite']} ≠ {name}")
        if inv == "self":
            if reg["reciprocity"] != "symmetric" or reg["direction"] != "bidirectional":
                violations.append(
                    f"{name}.inverse=self 但 reciprocity/direction 未对齐 (symmetric/bidirectional)")
    return (len(violations) == 0, violations)


def _as_triple(e):
    if isinstance(e, (list, tuple)) and len(e) == 3:
        return e[0], e[1], e[2]
    return e["source"], e["relation"], e["target"]


def smoke_test():
    idx, enum = registry_index()
    # --- RC-A: 多角色端点（不再只取主角色）---
    assert endpoint_ok("supports", {"record_type": "evidence"},
                        {"record_type": "evaluation_decision"}, idx)[0], "Evidence supports evaluation_decision 应 PASS"
    assert endpoint_ok("indicates", {"record_type": "observation_record"},
                        {"record_type": "observation_inference"}, idx)[0], "Signal indicates observation_inference 应 PASS"
    assert not endpoint_ok("supports", {"record_type": "intervention_pattern"},
                            {"record_type": "evaluation_decision"}, idx)[0], "Technique supports evaluation_decision 应 FAIL"
    # 未知 record_type → fail-closed（不再等同 Entity）
    assert not endpoint_ok("supports", {"record_type": "totally_unknown_xyz"},
                            {"record_type": "claim"}, idx)[0], "未知 record_type 应 FAIL"
    # --- RC-A: 单角色场景仍正确 ---
    assert endpoint_ok("supports", {"record_type": "evidence"}, {"record_type": "claim"}, idx)[0]
    assert not endpoint_ok("supports", {"record_type": "intervention_pattern"}, {"record_type": "claim"}, idx)[0]
    # --- RC-A: ANY 匹配已识别角色；未知即使 ANY 也 FAIL ---
    assert endpoint_ok("equivalent_to", {"record_type": "concept_model"},
                       {"record_type": "concept_model"}, idx)[0], "equivalent_to ANY 匹配"
    assert not endpoint_ok("equivalent_to", {"record_type": "unknown_rt"},
                            {"record_type": "unknown_rt"}, idx)[0], "未知即使 ANY 也 FAIL"
    # --- 互反性 ---
    assert reciprocity_violations([("a", "affects", "b"), ("b", "affects", "a")], idx) == []
    v = reciprocity_violations([("a", "precedes", "b"), ("b", "precedes", "a")], idx)
    assert len(v) == 1 and v[0][0] == "precedes" and set(v[0][1:]) == {"a", "b"}, v
    # --- 循环 ---
    viol, _ = cycle_violations([("a", "precedes", "b"), ("b", "precedes", "a")], idx)
    assert "precedes" in viol, viol
    viol2, conc2 = cycle_violations([("a", "requires", "b"), ("b", "requires", "a")], idx)
    assert "requires" in conc2 and "requires" not in viol2, (viol2, conc2)
    # --- RC-B: 多跳传递闭包（单次调用）---
    inf = transitive_inference("precedes",
                                [("a", "precedes", "b"), ("b", "precedes", "c"), ("c", "precedes", "d")], idx=idx)
    assert ("a", "d") in inf and ("a", "c") in inf and ("b", "d") in inf, inf
    assert len(inf) == 3, inf
    # --- RC-B: 双向对称传递（T1/T2/T3）---
    t1 = transitive_inference("equivalent_to", [("A", "equivalent_to", "B"), ("B", "equivalent_to", "C")], idx=idx)
    assert ("A", "C") in t1, t1
    t2 = transitive_inference("equivalent_to", [("B", "equivalent_to", "A"), ("B", "equivalent_to", "C")], idx=idx)
    assert ("A", "C") in t2, t2
    t3 = transitive_inference("equivalent_to", [("A", "equivalent_to", "B"), ("C", "equivalent_to", "B")], idx=idx)
    assert ("A", "C") in t3, t3
    # --- RC-B: 条件传递需要 guard；无 guard 不推断 ---
    cond_edges = [("cpu", "part_of", "mb"), ("mb", "part_of", "computer")]

    def allow_guard(relation, s, m, t):
        return "ALLOW"

    def deny_guard(relation, s, m, t):
        return "DENY"

    inf_allow = transitive_inference("part_of", cond_edges, guard_resolver=allow_guard, idx=idx)
    assert ("cpu", "computer") in inf_allow, inf_allow
    inf_none = transitive_inference("part_of", cond_edges, idx=idx)  # 无 guard
    assert inf_none == set(), inf_none
    inf_deny = transitive_inference("part_of", cond_edges, guard_resolver=deny_guard, idx=idx)
    assert ("cpu", "computer") not in inf_deny, inf_deny
    # --- RC-C: inverse/opposite 元数据完整性被消费 ---
    ok_meta, meta_v = relation_metadata_integrity(idx)
    assert ok_meta, meta_v
    print("[smoke_test] OK — Relation Audit Gate（RC-A/B/C 修复）基本断言通过")


if __name__ == "__main__":
    smoke_test()
    sys.exit(0)
