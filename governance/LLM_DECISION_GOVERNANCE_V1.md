# LLM Decision Governance V1

Status: project governance contract.

## Core rule

LLM may decide **how** to satisfy a task inside an allowed search space. LLM must not decide the minimum acceptable quality, tool usage floor, provider-safety boundary, or final delivery format when those decisions affect critical production assets.

`LLM_SEMANTIC_FREEDOM=true`

`LLM_EXECUTION_CRITICAL_DECISIONS_REQUIRE_CONTRACT=true`

`PHYSICAL_TOOL_AND_PROVIDER_ROUTING_DETERMINISTIC=true`

## Contract trigger

A machine-verifiable contract is required when an LLM decision can materially affect any of:

1. real provider spend;
2. logical tool class or generated-asset type;
3. number or proportion of core assets;
4. first-screen / first-three-second quality floor;
5. final dominant visual form;
6. cover existence or exact display title;
7. final canvas, subtitles, or delivery format;
8. whether downstream must invent creative decisions;
9. whether cost optimization can reduce a defined quality floor.

## Freedom levels

### Semantic freedom
Reasoning, narrative organization, language lowering, ordinary prompt wording, and scene selection may remain model-driven inside source/claim/boundary contracts.

### Bounded planning
Visual material planning may choose scenes, semantic motion requirements, logical asset strategy, continuity mode, and prompts, but it must satisfy hard machine contracts for first-segment video, HappyHorse quota, cover, timing, visual purity, and explicit motion parameters.

### Deterministic execution
Provider adapter, credentials, API route, retry semantics, polling, concurrency, dispatch, receipt validation, render dimensions, subtitle style, and exact cover typography are code/config owned.

## Anti-shortcut rule

When several outputs are contract-valid, the model must not optimize solely for minimum provider cost, minimum asset count, minimum motion, or easiest implementation unless the active policy explicitly makes that the dominant objective.

This guidance never replaces hard gates. Quality floors must be machine-enforced whenever they are objectively verifiable.

## Source-of-truth order

Provider/safety hard capability
>
Run policy snapshot
>
Machine contract/schema
>
LLM guidance
>
Stage prompt
>
LLM preference

The final project-level Control Plane and `LLM_GUIDE.md` are intentionally deferred until the new real production gate passes. They will be extracted from proven runtime policies rather than designed ahead of evidence.
