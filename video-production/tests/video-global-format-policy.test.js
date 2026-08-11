import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {VIDEO_FORMAT_POLICY,VIDEO_FORMAT,VIDEO_FORMAT_POLICY_ID,assertGlobalVideoFormat} from "../src/video-format-policy.js";

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"../../..");
const read=relative=>fs.readFileSync(path.join(root,relative),"utf8");
const json=relative=>JSON.parse(read(relative));
const inherited={policy_source:VIDEO_FORMAT_POLICY_ID,...VIDEO_FORMAT};

assert.deepEqual(VIDEO_FORMAT,{width:1280,height:720,resolution:"720p",aspect_ratio:"16:9"});
assert.equal(assertGlobalVideoFormat(inherited),inherited);
assert.throws(()=>assertGlobalVideoFormat({...inherited,aspect_ratio:"9:16"}),/Global video production format/);
assert.equal(VIDEO_FORMAT_POLICY.references.previous_asset_frame_inherits_video_format,true);
assert.equal(VIDEO_FORMAT_POLICY.references.generated_reference_target,"landscape_16_9");
assert.deepEqual(VIDEO_FORMAT_POLICY.image_motion,{output_width:1280,output_height:720,output_aspect_ratio:"16:9"});
assert.equal(VIDEO_FORMAT_POLICY.subtitles.primary_color,"white");
assert.equal(VIDEO_FORMAT_POLICY.subtitles.burned_in_generation,false);
assert.equal(VIDEO_FORMAT_POLICY.boundaries.final_platform_canvas_frozen,false);
assert.equal(VIDEO_FORMAT_POLICY.boundaries.cover_format_policy,"independent_unchanged");

const production=json("visual-script-module-probe-v1-evidence/production-script.json");
assert.deepEqual(production.video_format,inherited);
assert.equal(Object.hasOwn(production.cover_plan,"video_format"),false);
const productionSchema=json("video-visual-production-planner/schemas/production-script.schema.json");
assert.equal(productionSchema.properties.video_format.properties.aspect_ratio.const,"16:9");
const taskSchema=json("asset-dispatcher/schemas/asset-task.schema.json");
assert.equal(taskSchema.properties.input_requirements.properties.video_format.properties.resolution.const,"720p");

const planner=read("video-visual-production-planner/planners/asset-strategy-planner.md");
for(const phrase of ["never selects resolution or aspect ratio","TikTok, Reels, Shorts, Facebook vertical","1280x720, 720p, 16:9"])assert.ok(planner.includes(phrase));
const dispatcher=read("asset-dispatcher/dispatcher/dispatch-rules.md");
assert.ok(dispatcher.includes("不得覆盖、推断或依据 platform 改写"));
assert.ok(dispatcher.includes("Cover不继承此字段"));

process.stdout.write(JSON.stringify({
  GLOBAL_VIDEO_FORMAT_POLICY_BOUND:true,VIDEO_FRAME_WIDTH:1280,VIDEO_FRAME_HEIGHT:720,VIDEO_FRAME_QUALITY:"720p",VIDEO_FRAME_ASPECT_RATIO:"16:9",
  SINGLE_CANONICAL_VIDEO_FORMAT_SOURCE:true,PLANNER_GLOBAL_FORMAT_INHERITED:true,DISPATCHER_FORMAT_OVERRIDE:false,
  CONTINUITY_FORMAT_CONTRACT_PASS:true,IMAGE_MOTION_FORMAT_CONTRACT_PASS:true,SUBTITLE_PRIMARY_COLOR:"white",SUBTITLE_BURNED_IN_GENERATION:false,
  FINAL_PLATFORM_CANVAS_FROZEN:false,COVER_FORMAT_POLICY_UNCHANGED:true,REAL_PROVIDER_CALL:false,VIDEO_GENERATION:false,CREDITS_CONSUMED:false
},null,2)+"\n");
