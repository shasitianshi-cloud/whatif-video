#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

function esc(value) {
  return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function asSeconds(ms) { return Number(ms) / 1000; }

function projectRootAssetUrl(projectRoot, localPath) {
  const absolute = path.resolve(projectRoot, localPath);
  const root = path.resolve(projectRoot);
  if (absolute !== root && !absolute.startsWith(root + path.sep)) throw new Error(`asset outside project: ${localPath}`);
  return path.relative(root, absolute).split(path.sep).join('/');
}

function normalizeMotion(motion) {
  if (!motion || !motion.parameters || typeof motion.parameters !== 'object' || Array.isArray(motion.parameters)) {
    throw new Error('MOTION_PARAMETERS_REQUIRED');
  }
  const p = motion.parameters;
  const from = p.from && typeof p.from === 'object' && !Array.isArray(p.from) ? p.from : {
    x_percent: p.start_x_percent, y_percent: p.start_y_percent, scale: p.start_scale
  };
  const to = p.to && typeof p.to === 'object' && !Array.isArray(p.to) ? p.to : {
    x_percent: p.end_x_percent, y_percent: p.end_y_percent, scale: p.end_scale
  };
  const requireNumber = (value) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('INVALID_MOTION_PARAMETERS');
    return value;
  };
  const result = {
    from: {
      x_percent: requireNumber(from.x_percent),
      y_percent: requireNumber(from.y_percent),
      scale: requireNumber(from.scale),
    },
    to: {
      x_percent: requireNumber(to.x_percent),
      y_percent: requireNumber(to.y_percent),
      scale: requireNumber(to.scale),
    },
  };
  for (const side of ['from', 'to']) {
    if (!(result[side].scale > 0)) throw new Error('INVALID_MOTION_PARAMETERS');
    if (Math.abs(result[side].x_percent) > 100 || Math.abs(result[side].y_percent) > 100) throw new Error('INVALID_MOTION_PARAMETERS');
  }
  return result;
}

function assertVerticalLayout(renderPlan) {
  const composition = renderPlan.composition || {};
  const stage = renderPlan.layout?.content_stage || {};
  const subtitle = renderPlan.layout?.subtitles || {};
  if (
    composition.width !== 1280 ||
    composition.height !== 2276 ||
    composition.aspect_ratio !== '9:16' ||
    !(composition.duration_ms > 0)
  ) throw new Error('GLOBAL_VERTICAL_SHORT_VIDEO_LAYOUT_REQUIRED');
  if (
    stage.x !== 0 ||
    stage.y !== 778 ||
    stage.width !== 1280 ||
    stage.height !== 720
  ) throw new Error('CONTENT_STAGE_1280X720_REQUIRED');
  if (
    subtitle.font_size_px !== 52 ||
    subtitle.block_width_px !== 1080 ||
    subtitle.center_x_px !== 640 ||
    subtitle.center_y_px !== 1887 ||
    subtitle.region !== 'bottom_black_bar'
  ) throw new Error('SUBTITLE_BOTTOM_BAR_POLICY_REQUIRED');
  return { composition, stage, subtitle };
}

function buildComposition({ renderPlan, projectRoot, outputDir, fontPath }) {
  if (!renderPlan || renderPlan.schema_version !== 1) throw new Error('invalid render plan');
  const { composition, stage, subtitle } = assertVerticalLayout(renderPlan);
  const durationMs = composition.duration_ms;
  fs.mkdirSync(outputDir, { recursive: true });
  const fontUrl = projectRootAssetUrl(projectRoot, fontPath);
  const motionRecords = [];

  const visualHtml = renderPlan.layers.map((layer, index) => {
    const src = projectRootAssetUrl(projectRoot, layer.local_path);
    const start = asSeconds(layer.start_ms);
    const duration = asSeconds(layer.duration_ms);
    const id = `visual-${index}`;
    const commonStyle = `left:${stage.x}px;top:${stage.y}px;width:${stage.width}px;height:${stage.height}px;`;
    if (layer.treatment === 'direct_video') {
      return `<video id="${id}" class="hf-visual" style="${commonStyle}" src="${esc(src)}" data-start="${start}" data-duration="${duration}" data-track-index="1" muted playsinline preload="auto"></video>`;
    }
    if (layer.treatment === 'static_image') {
      return `<img id="${id}" class="hf-visual" style="${commonStyle}" src="${esc(src)}" data-start="${start}" data-duration="${duration}" data-track-index="1" />`;
    }
    if (layer.treatment === 'image_motion') {
      const resolved = normalizeMotion(layer.motion);
      motionRecords.push({ id, start, duration, ...resolved });
      return `<img id="${id}" class="hf-visual hf-motion" style="${commonStyle}" src="${esc(src)}" data-start="${start}" data-duration="${duration}" data-track-index="1" />`;
    }
    throw new Error(`unsupported treatment: ${layer.treatment}`);
  }).join('\n');

  const audioHtml = renderPlan.audio.map((a, index) => {
    const src = projectRootAssetUrl(projectRoot, a.local_path);
    return `<audio id="audio-${index}" src="${esc(src)}" data-start="${asSeconds(a.start_ms)}" data-duration="${asSeconds(a.duration_ms)}" data-track-index="10" preload="auto"></audio>`;
  }).join('\n');

  const subtitleHtml = renderPlan.subtitles.map((s, index) => {
    const start = asSeconds(s.start_ms);
    const duration = asSeconds(s.end_ms - s.start_ms);
    return `<div id="subtitle-${index}" class="hf-subtitle" data-start="${start}" data-duration="${duration}" data-track-index="20">${esc(s.text)}</div>`;
  }).join('\n');

  const html = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1280, height=2276" />
<style>
@font-face { font-family: 'Noto Sans CJK SC'; src: url('${esc(fontUrl)}') format('opentype'); font-weight: 400; font-style: normal; }
html,body { margin:0; width:100%; height:100%; overflow:hidden; background:#000; }
#root { position:relative; width:1280px; height:2276px; overflow:hidden; background:#000; }
.hf-visual { position:absolute; object-fit:cover; transform-origin:center center; overflow:hidden; }
.hf-subtitle {
  position:absolute;
  left:100px;
  width:${subtitle.block_width_px}px;
  top:${subtitle.center_y_px}px;
  transform:translateY(-50%);
  z-index:100;
  text-align:center;
  color:${esc(subtitle.primary_color || 'white')};
  font-family:'Noto Sans CJK SC',sans-serif;
  font-size:${subtitle.font_size_px}px;
  line-height:${subtitle.line_height};
  font-weight:${subtitle.font_weight || 400};
  overflow-wrap:anywhere;
}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-width="1280" data-height="2276" data-duration="${asSeconds(durationMs)}">
${visualHtml}
${audioHtml}
${subtitleHtml}
</div>
<script>
(() => {
  const motions = ${JSON.stringify(motionRecords)};
  let now = 0; let isPaused = true;
  function apply(t) {
    now = Math.max(0, Number(t) || 0);
    for (const m of motions) {
      const node = document.getElementById(m.id); if (!node) continue;
      const q = m.duration <= 0 ? 1 : Math.max(0, Math.min(1, (now - m.start) / m.duration));
      const x = m.from.x_percent + (m.to.x_percent - m.from.x_percent) * q;
      const y = m.from.y_percent + (m.to.y_percent - m.from.y_percent) * q;
      const scale = m.from.scale + (m.to.scale - m.from.scale) * q;
      node.style.transform = 'translate(' + x + '%, ' + y + '%) scale(' + scale + ')';
    }
  }
  const tl = {
    play(){ isPaused=false; return this; }, pause(){ isPaused=true; return this; },
    seek(t){ apply(t); return this; }, totalTime(t){ if (t !== undefined) apply(t); return now; },
    progress(v){ if (v !== undefined) apply(v * ${asSeconds(durationMs)}); return now / ${asSeconds(durationMs)}; },
    time(){ return now; }, duration(){ return ${asSeconds(durationMs)}; }, add(){ return this; },
    paused(v){ if (v !== undefined) isPaused=Boolean(v); return isPaused; }, timeScale(){ return 1; },
    set(){ return this; }, getChildren(){ return []; }
  };
  window.__timelines = window.__timelines || {}; window.__timelines.main = tl; apply(0);
})();
</script>
</body>
</html>
`;
  const outputPath = path.join(outputDir, 'index.html');
  fs.writeFileSync(outputPath, html);
  return {
    outputPath,
    motionCount: motionRecords.length,
    durationMs,
    finalCanvas: { width: 1280, height: 2276 },
    contentStage: { x: stage.x, y: stage.y, width: stage.width, height: stage.height },
    subtitleCenter: { x: subtitle.center_x_px, y: subtitle.center_y_px, fontSizePx: subtitle.font_size_px }
  };
}

module.exports = { buildComposition, normalizeMotion, projectRootAssetUrl, assertVerticalLayout };

if (require.main === module) {
  const [renderPlanPath, projectRootArg, outputDirArg] = process.argv.slice(2);
  if (!renderPlanPath || !projectRootArg || !outputDirArg) {
    console.error('usage: build-hyperframes-composition.js <render-plan.json> <project-root> <output-dir>');
    process.exit(2);
  }
  const projectRoot = path.resolve(projectRootArg);
  const outputDir = path.resolve(outputDirArg);
  const renderPlan = JSON.parse(fs.readFileSync(renderPlanPath, 'utf8'));
  const result = buildComposition({
    renderPlan,
    projectRoot,
    outputDir,
    fontPath: 'video-production/assets/fonts/NotoSansCJKsc-Regular.otf'
  });
  console.log(JSON.stringify(result));
}
