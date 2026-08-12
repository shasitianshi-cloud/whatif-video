# Anchor Program V1

Purpose: manage a sustainable daily entrypoint without either unrestricted LLM roaming or a fixed small anchor list.

## Runtime model

`Weekly Scope -> Daily 6 candidates -> bounded evaluation -> deterministic selection gate -> single Anchor -> Premise Discovery`

Weekly scope is human/control-plane owned. Daily anchor identity is LLM-selected inside the active scope.

## Hard boundaries

- exactly 6 daily candidates;
- candidates are object-level anchors only;
- no What-if, perturbation, Counterfactual Contract, or ranking in candidate generation;
- evaluation uses five 0-5 dimensions plus hard viability/scope/duplicate flags;
- total interest score is computed by code, not by the LLM;
- exact recent duplicates are rejected deterministically;
- LLM evaluator flags semantic rephrases/near-duplicates;
- same subscope cannot continue beyond the configured limit;
- Premise Discovery remains the only stage allowed to define the actual counterfactual.

## Interest dimensions

- curiosity: 30%
- recognizability: 15%
- consequence_depth: 25%
- visual_potential: 20%
- non_obviousness: 10%

Minimum weighted score: 3.5/5.

## History

Production may keep a small append-only `anchor-history.jsonl`. The selector reads only the configured recent window (30 days by default). This is a duplicate/diversity ledger, not a semantic memory system.

## Weekly operation

A weekly scope file defines the current theme and allowed subscopes, for example space, biology, cities, energy, oceans, or technology. The final Control Plane will own this field after the new real production gate passes.

This module does not schedule itself and does not call external providers. A daily scheduler may invoke it later.
