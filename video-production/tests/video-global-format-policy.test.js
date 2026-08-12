import assert from "node:assert/strict";
import {
  VIDEO_FORMAT_POLICY,
  VIDEO_FORMAT,
  FINAL_CANVAS,
  CONTENT_STAGE,
  SUBTITLE_POLICY,
  COVER_POLICY,
  VIDEO_FORMAT_POLICY_ID,
  assertGlobalVideoFormat,
  assertFinalCanvas
} from "../src/video-format-policy.js";

const inherited={policy_source:VIDEO_FORMAT_POLICY_ID,...VIDEO_FORMAT};

assert.deepEqual(VIDEO_FORMAT,{
  width:1280,
  height:720,
  resolution:"720p",
  aspect_ratio:"16:9",
  role:"content_stage_and_provider_frame"
});
assert.equal(assertGlobalVideoFormat(inherited),inherited);
assert.throws(()=>assertGlobalVideoFormat({...inherited,aspect_ratio:"9:16"}),/Global video production format/);

assert.deepEqual(FINAL_CANVAS,{width:1280,height:2276,aspect_ratio:"9:16",background:"black"});
assert.equal(assertFinalCanvas(FINAL_CANVAS),FINAL_CANVAS);
assert.throws(()=>assertFinalCanvas({width:1280,height:720,aspect_ratio:"16:9"}),/Global final canvas/);

assert.deepEqual(CONTENT_STAGE,{x:0,y:778,width:1280,height:720,aspect_ratio:"16:9",fit:"cover"});
assert.equal(VIDEO_FORMAT_POLICY.black_bars.top.height,778);
assert.equal(VIDEO_FORMAT_POLICY.black_bars.bottom.y,1498);
assert.equal(VIDEO_FORMAT_POLICY.black_bars.bottom.height,778);

assert.equal(SUBTITLE_POLICY.primary_color,"white");
assert.equal(SUBTITLE_POLICY.font_family,"Noto Sans CJK SC");
assert.equal(SUBTITLE_POLICY.font_size_px,52);
assert.equal(SUBTITLE_POLICY.block_width_px,1080);
assert.equal(SUBTITLE_POLICY.center_x_px,640);
assert.equal(SUBTITLE_POLICY.center_y_px,1887);
assert.equal(SUBTITLE_POLICY.region,"bottom_black_bar");
assert.equal(VIDEO_FORMAT_POLICY.boundaries.subtitle_over_content,false);

assert.equal(COVER_POLICY.required,true);
assert.equal(COVER_POLICY.canvas_width,1280);
assert.equal(COVER_POLICY.canvas_height,2276);
assert.equal(COVER_POLICY.title.font_size_px,96);
assert.equal(COVER_POLICY.title.center_y_px,1887);
assert.equal(VIDEO_FORMAT_POLICY.boundaries.cover_title_generated_by_image_model,false);
assert.equal(VIDEO_FORMAT_POLICY.boundaries.final_platform_canvas_frozen,true);

process.stdout.write(JSON.stringify({
  GLOBAL_VIDEO_FORMAT_POLICY_V2_BOUND:true,
  CONTENT_FRAME_WIDTH:1280,
  CONTENT_FRAME_HEIGHT:720,
  CONTENT_FRAME_ASPECT_RATIO:"16:9",
  FINAL_CANVAS_WIDTH:1280,
  FINAL_CANVAS_HEIGHT:2276,
  FINAL_CANVAS_ASPECT_RATIO:"9:16",
  SUBTITLE_FONT_SIZE_PX:52,
  SUBTITLE_REGION:"bottom_black_bar",
  COVER_TITLE_FONT_SIZE_PX:96,
  FINAL_PLATFORM_CANVAS_FROZEN:true,
  REAL_PROVIDER_CALL:false,
  VIDEO_GENERATION:false,
  CREDITS_CONSUMED:false
},null,2)+"\n");
