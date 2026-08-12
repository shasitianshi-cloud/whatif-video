#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const FORMAT_POLICY = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, '../config/video-format.json'), 'utf8')
);

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(k => [k, canonicalize(value[k])]));
  }
  return value;
}

function sha256Json(value) {
  return crypto.createHash('sha256').update(JSON.stringify(canonicalize(value))).digest('hex');
}

function compileRenderPlan(renderInput, assetManifest) {
  if (!renderInput || renderInput.schema_version !== 1) throw new Error('invalid render input schema');
  if (!assetManifest || assetManifest.run_id !== renderInput.run_id) throw new Error('CROSS_RUN_PRODUCTION_RENDER_FORBIDDEN');

  const frame = renderInput.content_frame || {};
  const source = FORMAT_POLICY.video;
  if (
    frame.width !== source.width ||
    frame.height !== source.height ||
    frame.aspect_ratio !== source.aspect_ratio
  ) {
    throw new Error('invalid content frame policy');
  }

  const canvas = FORMAT_POLICY.final_canvas;
  const stage = FORMAT_POLICY.content_stage;
  const subtitlePolicy = FORMAT_POLICY.subtitles;
  if (
    canvas.width !== 1280 ||
    canvas.height !== 2276 ||
    stage.width !== 1280 ||
    stage.height !== 720 ||
    stage.x !== 0 ||
    stage.y !== 778
  ) {
    throw new Error('GLOBAL_VERTICAL_SHORT_VIDEO_LAYOUT_REQUIRED');
  }

  const assets = new Map(assetManifest.assets.map(a => [a.asset_id, a]));
  const layers = [];
  const audio = [];
  let durationMs = 0;

  for (const segment of renderInput.timeline) {
    if (segment.end_ms !== segment.start_ms + segment.duration_ms) throw new Error('timeline disorder');
    durationMs = Math.max(durationMs, segment.end_ms);
    const audioAsset = assets.get(segment.audio_asset_id);
    if (!audioAsset || audioAsset.asset_kind !== 'audio') throw new Error('audio missing');
    audio.push({
      type: 'audio',
      asset_id: audioAsset.asset_id,
      local_path: audioAsset.local_path,
      sha256: audioAsset.sha256,
      start_ms: segment.start_ms,
      duration_ms: segment.duration_ms,
      end_ms: segment.end_ms,
      segment_id: segment.segment_id
    });

    for (const visual of segment.visual_assets) {
      const asset = assets.get(visual.asset_id);
      if (!asset) throw new Error(`asset missing: ${visual.asset_id}`);
      const common = {
        asset_id: asset.asset_id,
        local_path: asset.local_path,
        sha256: asset.sha256,
        start_ms: visual.start_ms,
        duration_ms: visual.duration_ms,
        end_ms: visual.end_ms,
        segment_id: segment.segment_id
      };
      if (visual.render_treatment === 'direct_video') {
        if (asset.asset_kind !== 'video') throw new Error('direct_video requires video');
        layers.push({
          type: 'video',
          treatment: 'direct_video',
          fit: 'cover',
          stage: canonicalize(stage),
          trim_mode: 'deterministic',
          ...common
        });
      } else if (visual.render_treatment === 'static_image') {
        if (asset.asset_kind !== 'image') throw new Error('static_image requires image');
        layers.push({
          type: 'image',
          treatment: 'static_image',
          fit: visual.fit || null,
          stage: canonicalize(stage),
          motion: null,
          ...common
        });
      } else if (visual.render_treatment === 'image_motion') {
        if (asset.asset_kind !== 'image') throw new Error('image_motion requires image');
        layers.push({
          type: 'image',
          treatment: 'image_motion',
          fit: visual.fit || null,
          stage: canonicalize(stage),
          motion: {
            intent: visual.motion_intent || 'UNRESOLVED',
            parameters: visual.motion_parameters ? canonicalize(visual.motion_parameters) : null
          },
          ...common
        });
      } else {
        throw new Error(`unsupported render treatment: ${visual.render_treatment}`);
      }
    }
  }

  const subtitles = renderInput.subtitles.map(s => ({
    type: 'subtitle',
    segment_id: s.segment_id,
    text: s.text,
    start_ms: s.start_ms,
    end_ms: s.end_ms,
    primary_color: s.primary_color || subtitlePolicy.primary_color,
    font_family: subtitlePolicy.font_family,
    font_size_px: subtitlePolicy.font_size_px,
    line_height: subtitlePolicy.line_height,
    block_width_px: subtitlePolicy.block_width_px,
    center_x_px: subtitlePolicy.center_x_px,
    center_y_px: subtitlePolicy.center_y_px,
    region: subtitlePolicy.region
  }));

  const plan = {
    schema_version: 1,
    run_id: renderInput.run_id,
    format_policy_id: FORMAT_POLICY.policy_id,
    composition: {
      width: canvas.width,
      height: canvas.height,
      aspect_ratio: canvas.aspect_ratio,
      duration_ms: durationMs,
      background: canvas.background
    },
    layout: {
      content_stage: canonicalize(stage),
      black_bars: canonicalize(FORMAT_POLICY.black_bars),
      subtitles: canonicalize(subtitlePolicy)
    },
    layers,
    audio,
    subtitles
  };
  plan.identity = {
    render_input_sha256: sha256Json(renderInput),
    asset_manifest_sha256: sha256Json(assetManifest)
  };
  return plan;
}

module.exports = { compileRenderPlan, canonicalize, sha256Json };

if (require.main === module) {
  const [renderInputPath, assetManifestPath, outputPath] = process.argv.slice(2);
  if (!renderInputPath || !assetManifestPath || !outputPath) {
    console.error('usage: hyperframes-render-compiler.js <render-input.json> <asset-manifest.json> <render-plan.json>');
    process.exit(2);
  }
  const renderInput = JSON.parse(fs.readFileSync(renderInputPath, 'utf8'));
  const assetManifest = JSON.parse(fs.readFileSync(assetManifestPath, 'utf8'));
  const plan = compileRenderPlan(renderInput, assetManifest);
  fs.writeFileSync(outputPath, JSON.stringify(plan, null, 2) + '\n');
}
