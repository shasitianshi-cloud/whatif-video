# Video Production — Foundation and Volcengine TTS V1

This phase consumes one explicitly supplied frozen `video-master.md`, verifies
its SHA-256 and the upstream freeze, segments it without rewriting, and creates
one measured narration audio artifact per segment.

The runtime credential is read only from `VOLCENGINE_TTS_API_KEY`. It must not
be placed in configuration, source, tests, manifests, or evidence.

Implemented boundary:

`frozen video master -> lossless segments -> narration plan -> Volcengine V3 -> ffprobe durations -> duration enforcement -> narration manifest -> completeness gate`

The final narration-unit limit is strictly `duration_ms < 15000`. Oversized
units alone are losslessly bisected at the preferred natural punctuation
(`；`, then `，`, then `：`) nearest the text midpoint. Child IDs append `a`/`b`
and retain `parent_segment_id` plus `split_depth`. Only child units receive new
TTS calls; already-valid audio is reused. Recursion stops at
`MAX_SPLIT_DEPTH=3`, after which the gate fails.

Superseded parent audio remains as evidence but is excluded from the final
plan, manifest, artifact count, and AV Compiler input.

AV compilation, visual planning, image/video generation, subtitles, rendering,
and the final video gate are outside this phase.
# Global content video format

All production video assets inherit the single canonical policy at `config/video-format.json`: 1280x720, 720p, 16:9. This applies to generated video, continuity inputs, and the normalized output contract for image-motion segments. It does not freeze the final platform canvas or change the independent cover policy. Subtitles remain a deterministic Render Compiler overlay and are never burned into generated assets.
