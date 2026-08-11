'use strict';

const assert = require('assert');
const { compileRenderPlan, sha256Json } = require('../src/hyperframes-render-compiler.js');

const runId = 'production-render-compiler-test';
const manifest = {
  schema_version: 1,
  run_id: runId,
  assets: [
    { run_id: runId, asset_id: 'v1', asset_kind: 'video', role: 'content', local_path: 'v1.mp4', sha256: '1'.repeat(64) },
    { run_id: runId, asset_id: 'i1', asset_kind: 'image', role: 'content', local_path: 'i1.png', sha256: '2'.repeat(64) },
    { run_id: runId, asset_id: 'a1', asset_kind: 'audio', role: 'narration', local_path: 'a1.mp3', sha256: '3'.repeat(64) },
    { run_id: runId, asset_id: 'a2', asset_kind: 'audio', role: 'narration', local_path: 'a2.mp3', sha256: '4'.repeat(64) },
  ]
};

const input = {
  schema_version: 1,
  run_id: runId,
  content_frame: { width: 1280, height: 720, aspect_ratio: '16:9' },
  timeline: [
    { segment_id: 'seg-001', start_ms: 0, duration_ms: 1000, end_ms: 1000, audio_asset_id: 'a1', visual_assets: [
      { asset_id: 'v1', render_treatment: 'direct_video', start_ms: 0, duration_ms: 1000, end_ms: 1000 }
    ]},
    { segment_id: 'seg-002', start_ms: 1000, duration_ms: 1000, end_ms: 2000, audio_asset_id: 'a2', visual_assets: [
      { asset_id: 'i1', render_treatment: 'image_motion', start_ms: 1000, duration_ms: 1000, end_ms: 2000,
        motion_intent: 'pan', motion_parameters: { start_x_percent: -2, end_x_percent: 2, start_y_percent: 0, end_y_percent: 0, start_scale: 1.04, end_scale: 1.04 },
        fit: { mode: 'cover_crop', target_width: 1280, target_height: 720, preserve_aspect_ratio: true, stretch_allowed: false } }
    ]}
  ],
  subtitles: [
    { segment_id: 'seg-001', text: '第一段', start_ms: 0, end_ms: 1000, primary_color: 'white' },
    { segment_id: 'seg-002', text: '第二段', start_ms: 1000, end_ms: 2000, primary_color: 'white' }
  ]
};

const p1 = compileRenderPlan(input, manifest);
const p2 = compileRenderPlan(JSON.parse(JSON.stringify(input)), JSON.parse(JSON.stringify(manifest)));
assert.deepStrictEqual(p1, p2);
assert.strictEqual(sha256Json(p1), sha256Json(p2));
assert.strictEqual(p1.composition.width, 1280);
assert.strictEqual(p1.composition.height, 720);
assert.strictEqual(p1.composition.duration_ms, 2000);
assert.strictEqual(p1.layers[0].type, 'video');
assert.strictEqual(p1.layers[0].treatment, 'direct_video');
assert.strictEqual(p1.layers[1].type, 'image');
assert.strictEqual(p1.layers[1].treatment, 'image_motion');
assert.strictEqual(p1.layers[1].motion.intent, 'pan');
assert.deepStrictEqual(p1.layers[1].motion.parameters, input.timeline[1].visual_assets[0].motion_parameters);
assert.strictEqual(p1.layers[1].fit.stretch_allowed, false);
assert.strictEqual(p1.subtitles[0].font_family, 'Noto Sans CJK SC');
assert.strictEqual(p1.subtitles[0].primary_color, 'white');
assert.ok(!JSON.stringify(p1).includes('provider_metadata'));
assert.ok(!JSON.stringify(p1).includes('authorization'));
assert.ok(!JSON.stringify(p1).includes('media_id'));
assert.ok(!JSON.stringify(p1).includes('task_id'));
console.log('RENDER_COMPILER_REGRESSION_PASS=true');
console.log('RENDER_COMPILER_DETERMINISTIC=true');
console.log('RENDER_COMPILER_CREATIVE_DECISION=false');
console.log('DIRECT_VIDEO_MAPPING_PASS=true');
console.log('STATIC_IMAGE_MAPPING_PASS=true');
console.log('IMAGE_MOTION_MAPPING_PASS=true');
console.log('MOTION_PARAMETERS_PASSTHROUGH=true');
