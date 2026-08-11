# WHAT-IF Video Disaster Recovery Restore V2

This archive is a disaster-recovery snapshot of the current `whatif-video/` Work state captured on 2026-08-11 (Asia/Taipei). It was created directly from the current Work project, not rebuilt from chat history, an old ZIP, or an earlier Library backup.

## Restore procedure

1. Extract the archive into a new Work project directory.
2. Validate every payload entry against `DISASTER_RECOVERY_FILE_MANIFEST_V2.json`. The manifest intentionally excludes its own self-hash; verify the manifest file separately using the archive SHA/metadata supplied with the snapshot.
3. Do not rewrite historical evidence.
4. Check `shared/upstream-freeze-v1.json`, `shared/upstream-freeze-v1-evidence.json`, and `video-production/narration-freeze-v1*.json` before resuming.
5. Runtime secrets are not included. Read `DISASTER_RECOVERY_SECRET_EXCLUSIONS.json`.
6. If the HappyHorse session was lost, reauthenticate.
7. The verified Work HappyHorse OAuth callback transport is `127.0.0.1:33897/callback`.
8. Do not restart HappyHorse protocol discovery.
9. Do not restart GPT-image-2 capability discovery. The latest confirmed execution route is recorded in the state file.
10. Local image-motion execution is cancelled. Ordinary static-image motion belongs to the final HyperFrames render layer; do not restore `IMAGE_MOTION_EXECUTION_CLOSURE_V1` as the next stage.
11. Resume at `VIDEO_ASSET_MANIFEST_AND_RENDER_INPUT_CLOSURE`, then proceed to the HyperFrames render execution path.

## Source-boundary warning

The user-defined sole backup source was `whatif-video/`. Current evidence files inside that tree reference sibling implementation paths such as `asset-executor/`, but those sibling directories were not inside the permitted source root and were not copied or reconstructed. Restore validation must not treat referenced evidence paths as proof that the referenced source code is present in this archive.

## Architecture correction

- `IMAGE_MOTION_LOCAL_EXECUTION_CANCELLED=true`
- `IMAGE_MOTION_EXECUTION_CLOSURE_V1=CANCELLED`
- `IMAGE_MOTION_EXECUTOR=HYPERFRAMES_RENDER_LAYER`
- Formal direction: static image artifact → final HyperFrames render → deterministic motion.
- HappyHorse remains reserved for genuinely generative dynamic video assets.
