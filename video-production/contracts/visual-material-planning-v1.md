# Visual Material Planning Contract V1

Status: canonical recovery contract

## Boundary

Input: current-run Video Master, narration segments/text/duration, global video format, available execution capabilities, cost policy, continuity capability.

Output: a dynamic visual material plan sufficient to lower into a same-run Production Script. This layer does not generate media, call providers, execute TTS, or render HyperFrames.

Provider credentials, OAuth state, task IDs, media IDs, and runtime secrets are forbidden inputs.

## Core architecture

Fixed: production stages. Dynamic: the structure of each video.

`Video Master -> Visual Director LLM -> dynamic Production Script -> deterministic execution`

`VISUAL_STRUCTURE_DYNAMIC=true`
`ONE_SEGMENT_ONE_ASSET_HARDCODED=false`

## Decision order

Every visual decision must follow:

`semantic intent -> visual situation -> required motion -> asset strategy -> execution provider`

The planner must first answer what the viewer should see to understand the current narration directly. It must not begin with provider or media-type selection.

`SEMANTIC_INTENT_PRECEDES_PROVIDER_SELECTION=true`

## Scene and asset count

Scenes follow semantic progression, not sentence boundaries, narration segment boundaries, or fixed seconds. One scene may span multiple narration segments; one narration segment may contain multiple visual assets when there are materially distinct visual events.

Create a new asset only when there is new visual information: semantic change, visible action, scene change, or other material visual change.

`ASSET_COUNT_SEMANTIC_DRIVEN=true`

## Cost and media strategy

Static-first policy:

1. If static composition fully carries the meaning, use `image` or `image_motion`.
2. If only camera-like motion is required (push, pull, pan, zoom, reframe) and internal objects need not truly move, use an image plus deterministic HyperFrames motion.
3. Use generated video only when meaning depends on real subject action, object state change, environmental change, behavior, physical motion, continuous action, or another event impossible to express with static imagery plus camera transform.

`STATIC_FIRST_WHEN_SEMANTICALLY_SUFFICIENT=true`
`GENERATIVE_VIDEO_ONLY_WHEN_MOTION_SEMANTICALLY_REQUIRED=true`
`IMAGE_MOTION_EXECUTOR=HYPERFRAMES_RENDER_LAYER`

`image_motion` always produces an image artifact; it must never be used as a substitute for real-world motion such as walking, falling, machine operation, flowing liquid, explosion, or causal scene change.

## Generated video

Before selecting generated video, define: subject, action, environment, state/change, camera relationship.

Prompts describe visible events and facts, not explanations of the narration. Do not add subtitles, titles, explanation text, UI, infographic elements, arrows, or camera-instruction overlays. Naturally occurring scene text may remain.

## T2V / I2V / reference

For generated video:

- no required continuity with prior formal asset -> T2V candidate;
- required continuity of person/environment/subject/composition/visual state -> `previous_asset_frame` -> I2V;
- explicit subject must be established but there is no previous asset -> `generated_reference` -> I2V.

Do not generate reference images merely to force I2V.

`GENERATED_REFERENCE_ONLY_WHEN_REQUIRED=true`

## Continuity

Continuity is semantic-driven, not default. New place, time, subject, or situation may clean-cut into a new scene. Within one continuing scene, changed-world state must persist into subsequent shots unless the Video Master explicitly switches scene/time.

`CONTINUITY_SEMANTIC_DRIVEN=true`

## Visual prompts

Prompts are derived from the formal visual plan, not copied from narration text. They describe visible facts: subject, action, environment, objects, relevant lighting/time, composition, and necessary camera behavior. Abstract claims must first be lowered into concrete visible situations.

When content says only a generic person with no identity constraint, default to an Asian person. If generated text is genuinely required, default to Simplified Chinese. Do not proactively add text to ordinary visual assets and do not impose a global East-Asian visual style.

## Video-bound visual purity

Generated references, image-motion source images, and generated-video prompts must remain purely visual. Prohibited proactive overlays include titles, subtitles, numbering, corner labels, arrows, camera icons, camera instructions, explanatory copy, UI, and infographic elements. Natural text already belonging to the scene is allowed.

`VIDEO_BOUND_VISUAL_PURITY=true`

## Style

No fixed global `cinematic`, `anime`, `documentary`, or `commercial` template. Style derives from current content and scene. Continuing scenes should remain visually coherent; unrelated videos need not share one style.

## Timing

Narration duration is timing truth. Asset count follows semantic density and visual change, not duration alone.

If a narration segment uses multiple assets, each asset must have explicit `start_offset_ms` and `duration_ms`; their coverage must exactly equal the corresponding narration coverage. No downstream component may average or invent timing.

`EXPLICIT_MULTI_ASSET_TIMING_REQUIRED=true`

HappyHorse assets must remain inside the currently validated provider duration capability. If an action exceeds one-task capability, the Planner changes the visual structure explicitly; the Executor must not improvise a split.

## Cover

Cover is independently planned when required, with its own visual concept/prompt/composition. It is not inferred from the first content asset and does not enter the content timeline.

## Transition semantics

Planner outputs semantic transition intent only, such as `continue_scene` or `cut`. Pixel transition parameters and concrete HyperFrames transition values belong to Render Compiler.

## Downstream completeness

The resulting Production Script must make Dispatcher, Executor, and Render Input Builder deterministic. They must not decide whether to replace images with video, add assets, choose scenes, rewrite prompts, or otherwise re-plan creatively.

`DOWNSTREAM_CREATIVE_REPLANNING_REQUIRED=false`

## Prohibited architecture

Do not create a Director Runtime, Planner State Machine, Visual Memory Service, Scene Registry, Agent Supervisor, or equivalent orchestration layer for this contract.
