import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";

const file=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"../config/video-format.json");
export const VIDEO_FORMAT_POLICY=deepFreeze(JSON.parse(fs.readFileSync(file,"utf8")));
export const VIDEO_FORMAT=VIDEO_FORMAT_POLICY.video;
export const FINAL_CANVAS=VIDEO_FORMAT_POLICY.final_canvas;
export const CONTENT_STAGE=VIDEO_FORMAT_POLICY.content_stage;
export const SUBTITLE_POLICY=VIDEO_FORMAT_POLICY.subtitles;
export const COVER_POLICY=VIDEO_FORMAT_POLICY.cover;
export const VIDEO_FORMAT_POLICY_ID=VIDEO_FORMAT_POLICY.policy_id;

export function assertGlobalVideoFormat(value) {
  if(
    value?.width!==VIDEO_FORMAT.width ||
    value?.height!==VIDEO_FORMAT.height ||
    value?.resolution!==VIDEO_FORMAT.resolution ||
    value?.aspect_ratio!==VIDEO_FORMAT.aspect_ratio ||
    value?.policy_source!==VIDEO_FORMAT_POLICY_ID
  ) throw new Error("Global video production format required");
  return value;
}

export function assertFinalCanvas(value) {
  if(
    value?.width!==FINAL_CANVAS.width ||
    value?.height!==FINAL_CANVAS.height ||
    value?.aspect_ratio!==FINAL_CANVAS.aspect_ratio
  ) throw new Error("Global final canvas required");
  return value;
}

function deepFreeze(value) {
  Object.freeze(value);
  for(const child of Object.values(value)) {
    if(child&&typeof child==="object"&&!Object.isFrozen(child)) deepFreeze(child);
  }
  return value;
}
