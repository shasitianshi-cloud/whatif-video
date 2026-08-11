import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";

const file=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"../config/video-format.json");
export const VIDEO_FORMAT_POLICY=deepFreeze(JSON.parse(fs.readFileSync(file,"utf8")));
export const VIDEO_FORMAT=VIDEO_FORMAT_POLICY.video;
export const VIDEO_FORMAT_POLICY_ID=VIDEO_FORMAT_POLICY.policy_id;

export function assertGlobalVideoFormat(value) {
  if(value?.width!==VIDEO_FORMAT.width || value?.height!==VIDEO_FORMAT.height || value?.resolution!==VIDEO_FORMAT.resolution || value?.aspect_ratio!==VIDEO_FORMAT.aspect_ratio || value?.policy_source!==VIDEO_FORMAT_POLICY_ID) throw new Error("Global video production format required");
  return value;
}

function deepFreeze(value) { Object.freeze(value); for(const child of Object.values(value)) if(child&&typeof child==="object"&&!Object.isFrozen(child))deepFreeze(child); return value; }
