'use strict';

const assert = require('assert');
const { compileRenderPlan, sha256Json } = require('../src/hyperframes-render-compiler.js');

const runId = 'production-render-compiler-v2-test';
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
        motion_intent: 'pan', motion_parameters: { from: {x_percent:-2,y_percent:0,scale:1.04}, to:{x_percent:2,y_percent:0,scale:1.04} },
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
assert.strictEqual(p1.format_policy_id, 'global-video-production-format.v2');
assert.strictEqual(p1.composition.width, 1280);
assert.strictEqual(p1.composition.height, 2276);
assert.strictEqual(p1.composition.aspect_ratio, '9:16');
assert.strictEqual(p1.composition.duration_ms, 2000);
assert.deepStrictEqual(p1.layout.content_stage, {x:0,y:778,width:1280,height:720,aspect_ratio:'16:9',fit:'cover'});
assert.strictEqual(p1.layers[0].stage.y, 778);
assert.strictEqual(p1.layers[0].type, 'video');
assert.strictEqual(p1.layers[0].treatment, 'direct_video');
assert.strictEqual(p1.layers[1].type, 'image');
assert.strictEqual(p1.layers[1].treatment, 'image_motion');
assert.strictEqual(p1.layers[1].motion.intent, 'pan');
assert.deepStrictEqual(p1.layers[1].motion.parameters, input.timeline[1].visual_assets[0].motion_parameters);
assert.strictEqual(p1.layers[1].fit.stretch_allowed, false);
assert.strictEqual(p1.subtitles[0].font_family, 'Noto Sans CJK SC');
assert.strictEqual(p1.subtitles[0].font_size_px, 52);
assert.strictEqual(p1.subtitles[0].block_width_px, 1080);
assert.strictEqual(p1.subtitles[0].center_y_px, 1887);
assert.strictEqual(p1.subtitles[0].region, 'bottom_black_bar');
assert.ok(!JSON.stringify(p1).includes('provider_metadata'));
assert.ok(!JSON.stringify(p1).includes('authorization'));
assert.ok(!JSON.stringify(p1).includes('media_id'));
assert.ok(!JSON.stringify(p1).includes('task_id'));
console.log('RENDER_COMPILER_V2_REGRESSION_PASS=true');
console.log('FINAL_CANVAS=1280x2276');
console.log('CONTENT_STAGE=1280x720');
console.log('SUBTITLE_FONT_SIZE=52');
console.log('SUBTITLE_REGION=bottom_black_bar');
console.log('RENDER_COMPILER_CREATIVE_DECISION=false');
