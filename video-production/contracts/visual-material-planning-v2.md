# Visual Material Planning Contract V2

Status: global production contract.

## Boundary

Input: current-run Video Master, measured narration segments, counterfactual display title, execution capabilities, content-frame policy, and visual-planning policy.

Output: one complete Production Script. This layer does not call providers or render.

`LLM_SEMANTIC_FREEDOM=true`
`LLM_EXECUTION_CRITICAL_DECISIONS_REQUIRE_CONTRACT=true`
`DOWNSTREAM_CREATIVE_REPLANNING_REQUIRED=false`

## Decision order

`semantic intent -> visual situation -> required real motion -> asset strategy -> logical execution route`

The planner may choose scenes and prompts, but hard production floors are not optional.

## HappyHorse quota

Let `N = narration segment count`.

Required HappyHorse-primary segments:

`ceil(N * 0.40)`

A narration segment counts as HappyHorse-primary only when:

`generated_video_duration / narration_segment_duration > 0.50`

The first narration segment must be HappyHorse-primary and counts toward the quota.

`HAPPYHORSE_MIN_RATIO=0.40`
`HAPPYHORSE_QUOTA_ROUNDING=ceil`
`HAPPYHORSE_PRIMARY_THRESHOLD_EXCLUSIVE=0.50`
`FIRST_SEGMENT_HAPPYHORSE_REQUIRED=true`

Static-first cost preference applies only after the above hard quota is satisfied.

## First-three-second hook

The first timeline visual must:
- start at 0 ms;
- be `generated_video`;
- use `happyhorse`;
- cover at least the first 3000 ms;
- expose a structured `hook_contract`.

The hook contract must define:
- `visible_event`
- `dominant_subject`
- `state_change`
- `real_motion`
- `camera_relationship`
- `first_3s_visible_fact`
- `why_static_is_insufficient`

The first three seconds must present the core changed-world state or a directly connected high-impact visible event immediately. Do not use a neutral establishing shot, slow setup, or delayed reveal as the first-three-second plan.

Machine validation proves route/timing/structure. Semantic visual impact remains an LLM quality responsibility inside the contract; no fake numeric "impact score" is introduced.

## Asset strategy

Use `generated_video` for the first segment and enough additional segments to satisfy the quota.

After quota satisfaction:
- `image` when a still image is sufficient;
- `image_motion` when only deterministic camera-like motion is needed;
- `generated_video` when real internal action/state/environmental motion materially carries meaning.

`image_motion` must never substitute for real subject action or causal state change.

## Tool boundary

Planner chooses only logical asset strategy and, for HappyHorse, T2V/I2V/R2V continuity mode.

Physical provider, API endpoint, credentials, retry semantics, polling, and concurrency are deterministic runtime concerns and may not be selected by the planner.

## Timing

Narration duration is timing truth. Multi-asset coverage must be exact, gap-free, and ordered. HappyHorse task durations must remain within validated provider capability.

## Visual purity

Prompts describe visible facts only. No proactive subtitle, title, labels, arrows, UI, infographic, or camera-instruction overlays in video-bound generation.

## Cover

Cover is mandatory and outside the content timeline.

Planner supplies:
- theme-aligned background visual intent;
- pure visual background prompt;
- exact `title_text`, copied from the supplied `counterfactual_display_title`.

The background image generator must not draw the title. Exact cover title typography belongs to deterministic cover rendering.

`COVER_REQUIRED=true`
`COVER_TITLE_EXACT_SOURCE=counterfactual_display_title`
`GENERATED_COVER_TEXT_FORBIDDEN=true`

## Downstream

Dispatcher, Executor, Render Input Builder, Render Compiler, and Cover Renderer must not re-plan scenes, change asset types, rewrite prompts, change HappyHorse quota, or invent missing motion/timing.
