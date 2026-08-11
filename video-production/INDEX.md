# Video Production Index

## Active implementation

- `INDEX.md` — authoritative inventory for this phase.
- `README.md` — phase boundary and execution contract.
- `config/tts.json` — non-sensitive Volcengine TTS V3 configuration.
- `src/segment_video_master.py` — deterministic, lossless sentence segmenter.
- `src/tts_adapter.py` — Volcengine V3 audio generation and ffprobe measurement adapter.
- `src/orchestrator.py` — narration-production chain and final duration/completeness gate.
- `tests/test_segment_video_master.py` — lossless segmentation regression tests.
- `tests/test_tts_contract.py` — adapter safety and contract tests.
- `tests/test_narration_duration_gate.py` — strict duration, lossless resplit, depth, and superseded-parent tests.

## Runtime artifacts

- `../runs/<run_id>/video-production/narration/narration-plan.json`
- `../runs/<run_id>/video-production/narration/audio/seg-NNN[ab...].mp3`
- `../runs/<run_id>/video-production/narration/narration-audio-manifest.json`
- `../runs/<run_id>/video-production/narration/narration-completeness-gate.json`
- `../runs/<run_id>/video-production/narration/evidence.json`

## Active narration freeze

- `narration-freeze-v1.json` — authoritative Narration/TTS production baseline freeze record.
- `narration-freeze-v1-evidence.json` — read-only revalidation evidence, formal MP3 digests, durations, and bounded implementation inventory.

```text
CURRENT_STAGE=NARRATION_FROZEN
NEXT_STAGE=AV_COMPILER
INTERMEDIATE_GATE_POLICY=NO_NEW_GATE_UNTIL_FINAL_VIDEO
NO_INTERMEDIATE_FREEZE_UNTIL_FINAL_VIDEO=true
```

The next permitted formal gate is `FINAL_VIDEO_GATE` after a complete video is actually generated; the next permitted project freeze is `FINAL_PROJECT_FREEZE`. Intermediate engineering modules may emit tests, probes, validation, evidence, blockers, and failure states, but must not introduce a new `*_GATE` or intermediate freeze.

Only paths that exist in the completed implementation may remain in this index.
