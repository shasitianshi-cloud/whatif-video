# Visual Material Planning Regression Reference V1

These fixtures validate semantic planning rules only. They do not generate media or call providers.

A. A person stands in a room thinking, with no real action requirement.
Expected: `image` or `image_motion` preferred; generated video is not required.

B. A person walks from an office onto the street.
Expected: generated-video candidate because the meaning depends on real continuous subject movement.

C. The next shot continues the same person's action from the prior formal video asset.
Expected: semantic continuity; `previous_asset_frame` dependency; I2V candidate.

D. The narrative cuts to a completely different city, time, or situation.
Expected: new scene / clean cut; no continuity dependency forced.

E. Abstract narration: “society begins changing identity-verification methods.”
Expected: lower into a concrete observable scene; do not produce an abstract infographic or explanatory overlay.

F. One 12-second narration segment contains one stable visual idea with no material visual change.
Expected: do not split into multiple assets solely because of duration.

G. One 8-second narration segment contains two materially distinct visual events.
Expected: multiple assets are allowed; every asset must have explicit `start_offset_ms` and `duration_ms`; coverage equals narration duration with no averaging downstream.

H. Static city panorama with a slow visual push.
Expected: `image_motion`; image artifact remains the source; HappyHorse is not called for the camera-like motion.

I. A machine is visibly operating and that operation is semantically necessary.
Expected: generated-video candidate; `image_motion` is insufficient.

J. Cover requested.
Expected: independently planned cover with `in_content_timeline=false`; it is not inferred from the first content asset.

Required invariants:

- `VISUAL_STRUCTURE_DYNAMIC=true`
- `ONE_SEGMENT_ONE_ASSET_HARDCODED=false`
- `SEMANTIC_INTENT_PRECEDES_PROVIDER_SELECTION=true`
- `ASSET_COUNT_SEMANTIC_DRIVEN=true`
- `STATIC_FIRST_WHEN_SEMANTICALLY_SUFFICIENT=true`
- `GENERATIVE_VIDEO_ONLY_WHEN_MOTION_SEMANTICALLY_REQUIRED=true`
- `IMAGE_MOTION_EXECUTOR=HYPERFRAMES_RENDER_LAYER`
- `CONTINUITY_SEMANTIC_DRIVEN=true`
- `GENERATED_REFERENCE_ONLY_WHEN_REQUIRED=true`
- `VIDEO_BOUND_VISUAL_PURITY=true`
- `EXPLICIT_MULTI_ASSET_TIMING_REQUIRED=true`
- `DOWNSTREAM_CREATIVE_REPLANNING_REQUIRED=false`
