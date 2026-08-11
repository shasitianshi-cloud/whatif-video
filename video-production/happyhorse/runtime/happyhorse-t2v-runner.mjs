import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {buildDownloadMetadataPath} from './watermark-control.mjs';

const API = 'https://api-gateway.aorizon.com/api';
const REFRESH_SKEW_MS = 60000;
const AUTH_REPLAY_CODES = new Set(['2005', '40102']);
const TERMINAL_REFRESH_CODES = new Set(['2004', '2005', '2006', '2022', '2023']);

const nowIso = () => new Date().toISOString();
const shaText = value => crypto.createHash('sha256').update(String(value), 'utf8').digest('hex');
const shaFile = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');

function atomicJson(file, value, mode = 0o600) {
  fs.mkdirSync(path.dirname(file), {recursive: true, mode: 0o700});
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(value, null, 2) + '\n', {mode});
  fs.renameSync(tmp, file);
  fs.chmodSync(file, mode);
}

function loadJson(file) { return JSON.parse(fs.readFileSync(file, 'utf8')); }
function scalar(v) { return (typeof v === 'string' || typeof v === 'number') ? String(v).slice(0, 128) : null; }
function diag(res, body) { return {http_status: res?.status ?? null, provider_error_code: scalar(body?.errorCode), trace_id: scalar(body?.traceId)}; }

function normalizeSession(raw) {
  return {
    appId: raw.appId ?? raw.app_id ?? 'aorizon_cn',
    deviceId: raw.deviceId ?? raw.device_id ?? null,
    accessToken: raw.accessToken ?? raw.access_token ?? null,
    refreshToken: raw.refreshToken ?? raw.refresh_token ?? null,
    accessExpiresAt: raw.accessExpiresAt ?? raw.access_expires_at ?? raw.accessExpiryMs ?? raw.expires_at ?? null,
    refreshExpiresAt: raw.refreshExpiresAt ?? raw.refresh_expires_at ?? raw.refreshExpiryMs ?? null,
  };
}

function commonHeaders(session, command, withAuth = true) {
  const h = {
    'User-Agent': 'happyhorse-cli/0.1.9',
    'X-App-Id': session.appId || 'aorizon_cn',
    'X-Language': 'zh-CN',
    'X-Client-Type': 'cli',
    'X-Client-Version': '0.1.9',
    'X-Client-Command': command,
  };
  if (session.deviceId) h['X-Device-Id'] = session.deviceId;
  if (withAuth) h.Authorization = `Bearer ${session.accessToken}`;
  return h;
}

async function rawJson(session, method, endpoint, command, body, {timeoutMs = 30000, withAuth = true} = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(`${API}${endpoint}`, {
      method,
      headers: {...commonHeaders(session, command, withAuth), ...(body !== undefined ? {'Content-Type': 'application/json'} : {})},
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } finally { clearTimeout(timer); }
  let parsed;
  try { parsed = await res.json(); }
  catch {
    const e = new Error('response parse interruption');
    e.responseReceived = true;
    e.httpStatus = res.status;
    throw e;
  }
  return {res, body: parsed};
}

function unwrap(res, body, operation) {
  if (!res.ok || body?.success === false) {
    const e = new Error(`${operation} provider rejection`);
    e.provider = true;
    e.diagnostics = diag(res, body);
    throw e;
  }
  if (!body || typeof body !== 'object') throw new Error(`${operation} invalid JSON envelope`);
  return body.data ?? body;
}

async function refreshSession(session, sessionPath, command) {
  if (!session.refreshToken) throw new Error('HAPPYHORSE_REFRESH_TOKEN_MISSING');
  if (Number.isFinite(Number(session.refreshExpiresAt)) && Number(session.refreshExpiresAt) <= Date.now()) {
    throw new Error('HAPPYHORSE_REFRESH_EXPIRED');
  }
  const {res, body} = await rawJson(session, 'POST', '/v1/auth/token/refresh', command, {refreshToken: session.refreshToken}, {withAuth: false});
  const code = scalar(body?.errorCode);
  if (!res.ok || body?.success === false) {
    const e = new Error(TERMINAL_REFRESH_CODES.has(code) || [401, 403].includes(res.status) ? 'HAPPYHORSE_REFRESH_TERMINAL_REJECTION' : 'HAPPYHORSE_REFRESH_FAILED');
    e.provider = true;
    e.diagnostics = diag(res, body);
    throw e;
  }
  const data = body?.data ?? body;
  if (!data?.accessToken || !data?.refreshToken || !Number.isFinite(Number(data?.accessExpiresIn)) || !Number.isFinite(Number(data?.refreshExpiresIn))) {
    throw new Error('HAPPYHORSE_REFRESH_RESPONSE_INVALID');
  }
  const receivedAt = Date.now();
  const next = {
    appId: session.appId || 'aorizon_cn',
    ...(session.deviceId ? {deviceId: session.deviceId} : {}),
    accessToken: data.accessToken,
    refreshToken: data.refreshToken,
    accessExpiresAt: receivedAt + Number(data.accessExpiresIn) * 1000,
    refreshExpiresAt: receivedAt + Number(data.refreshExpiresIn) * 1000,
  };
  atomicJson(sessionPath, next, 0o600);
  return next;
}

async function requestJson(sessionRef, sessionPath, method, endpoint, command, body, opts = {}) {
  if (Number.isFinite(Number(sessionRef.value.accessExpiresAt)) && Number(sessionRef.value.accessExpiresAt) - Date.now() <= REFRESH_SKEW_MS) {
    sessionRef.value = await refreshSession(sessionRef.value, sessionPath, command);
  }
  let response = await rawJson(sessionRef.value, method, endpoint, command, body, opts);
  const code = scalar(response.body?.errorCode);
  if (response.res.status === 401 || AUTH_REPLAY_CODES.has(code)) {
    sessionRef.value = await refreshSession(sessionRef.value, sessionPath, command);
    response = await rawJson(sessionRef.value, method, endpoint, command, body, opts);
  }
  return response;
}

function validateTask(task) {
  if (!task || typeof task !== 'object') throw new Error('TASK_REQUIRED');
  if (task.generation_route !== 'happyhorse' || task.expected_asset_kind !== 'video') throw new Error('HAPPYHORSE_T2V_ROUTE_MISMATCH');
  if (task.generation_mode !== 'T2V') throw new Error('HAPPYHORSE_T2V_MODE_REQUIRED');
  if (!task.run_id || !task.task_id || !task.asset_id || !task.prompt) throw new Error('HAPPYHORSE_T2V_TASK_IDENTITY_REQUIRED');
  const durationMs = Number(task.duration_ms);
  if (!Number.isSafeInteger(durationMs) || durationMs < 3000 || durationMs > 15000 || durationMs % 1000 !== 0) throw new Error('HAPPYHORSE_DURATION_UNSUPPORTED');
  const continuityKind = task.continuity?.kind ?? 'none';
  if (continuityKind !== 'none') throw new Error('T2V_CONTINUITY_MUST_BE_NONE');
  return {
    projectBody: {name: `CLI T2V <ISO timestamp>`, description: task.prompt},
    taskBody: {
      projectId: '<PROJECT_ID>', prompt: task.prompt, taskType: 'T2V',
      parameters: {durationS: durationMs / 1000, aspectRatio: '16:9', resolution: '720p', modelVersion: '1.5', shotType: 'single', sourceChannel: 'cli'},
      concurrency: 1,
    }
  };
}

async function execute(task, projectRoot) {
  validateTask(task);
  const sessionPath = path.join(projectRoot, '.runtime-auth/happyhorse/session.json');
  if (!fs.existsSync(sessionPath)) throw new Error('HAPPYHORSE_SESSION_MISSING');
  if ((fs.statSync(sessionPath).mode & 0o777) !== 0o600) throw new Error('HAPPYHORSE_SESSION_PERMISSION_INVALID');
  const sessionRef = {value: normalizeSession(loadJson(sessionPath))};
  if (!sessionRef.value.accessToken || !sessionRef.value.refreshToken) throw new Error('HAPPYHORSE_SESSION_FIELDS_MISSING');

  const outDir = path.join(projectRoot, 'runs', task.run_id, 'video-production', 'execution', task.asset_id);
  const statePath = path.join(outDir, '.happyhorse-t2v-state.json');
  const videoPath = path.join(outDir, `${task.asset_id}.mp4`);
  const artifactPath = path.join(outDir, `${task.asset_id}.artifact.json`);
  fs.mkdirSync(outDir, {recursive: true, mode: 0o700});
  let state = fs.existsSync(statePath) ? loadJson(statePath) : {};
  let membershipStatus;
  let projectId = state.project_id ?? null;
  let taskId = state.provider_task_id ?? null;
  const statusHistory = [];

  try {
    {
      const {res, body} = await requestJson(sessionRef, sessionPath, 'GET', '/v1/cli/membership/status', 'membership-status');
      membershipStatus = unwrap(res, body, 'membership');
    }

    if (!projectId) {
      if (state.project_create_started) throw new Error('AMBIGUOUS_PROJECT_SUBMISSION');
      state = {...state, project_create_started: true, project_create_started_at: nowIso()}; atomicJson(statePath, state);
      const projectBody = {name: `CLI T2V ${nowIso()}`, description: task.prompt};
      const {res, body} = await requestJson(sessionRef, sessionPath, 'POST', '/v2/projects', 'text2video', projectBody);
      const data = unwrap(res, body, 'project create');
      if (!data?.id) throw new Error('PROJECT_ID_ABSENT');
      if (data.status !== 'ACTIVE') throw new Error(`PROJECT_NOT_ACTIVE:${data.status ?? 'absent'}`);
      projectId = String(data.id);
      state = {...state, project_id: projectId, project_status: data.status, project_response_at: nowIso()}; atomicJson(statePath, state);
    }

    if (!taskId) {
      if (state.task_create_started) throw new Error('AMBIGUOUS_TASK_SUBMISSION');
      state = {...state, task_create_started: true, task_create_started_at: nowIso(), task_create_attempt_count: 1}; atomicJson(statePath, state);
      const taskBody = {
        projectId, prompt: task.prompt, taskType: 'T2V',
        parameters: {durationS: task.duration_ms / 1000, aspectRatio: '16:9', resolution: '720p', modelVersion: '1.5', shotType: 'single', sourceChannel: 'cli'},
        concurrency: 1,
      };
      let response;
      try { response = await requestJson(sessionRef, sessionPath, 'POST', '/v2/cli/tasks', 'text2video', taskBody, {timeoutMs: 30000}); }
      catch (e) { throw Object.assign(new Error('AMBIGUOUS_TASK_SUBMISSION'), {cause: e}); }
      const {res, body} = response;
      if (res.status >= 500) throw new Error('AMBIGUOUS_TASK_SUBMISSION');
      if (!res.ok || body?.success === false) {
        const e = new Error('TASK_CREATE_PROVIDER_REJECTION'); e.provider = true; e.diagnostics = diag(res, body); throw e;
      }
      const data = body?.data ?? body;
      if (!data?.id) throw new Error('AMBIGUOUS_TASK_SUBMISSION');
      taskId = String(data.id);
      state = {...state, provider_task_id: taskId, task_create_response_at: nowIso(), task_initial_status: data.status ?? 'QUEUED'}; atomicJson(statePath, state);
    }

    const protocol = loadJson(path.join(projectRoot, 'video-production/happyhorse/contracts/happyhorse-production-protocol-v1.json'));
    const inProgress = new Set(protocol.task_query.status_groups.in_progress);
    const success = new Set(protocol.task_query.status_groups.success);
    const failure = new Set(protocol.task_query.status_groups.failure);
    const deadline = Date.now() + 30 * 60 * 1000;
    let taskData;
    while (Date.now() < deadline) {
      const {res, body} = await requestJson(sessionRef, sessionPath, 'GET', `/v2/cli/tasks/${encodeURIComponent(taskId)}`, 'task', undefined, {timeoutMs: 30000});
      taskData = unwrap(res, body, 'task query');
      const raw = String(taskData?.status ?? '');
      if (!raw) throw new Error('PROVIDER_TASK_STATUS_ABSENT');
      if (statusHistory.at(-1) !== raw) statusHistory.push(raw);
      if (success.has(raw)) break;
      if (failure.has(raw)) throw new Error(`PROVIDER_TERMINAL_TASK_FAILURE:${raw}`);
      if (!inProgress.has(raw)) throw new Error(`UNKNOWN_PROVIDER_TASK_STATUS:${raw}`);
      await new Promise(resolve => setTimeout(resolve, 10000));
    }
    if (!taskData || !success.has(String(taskData.status))) throw new Error('TASK_POLL_DEADLINE_EXCEEDED');

    let signed = null;
    const metadataDeadline = Date.now() + 5 * 60 * 1000;
    while (Date.now() < metadataDeadline) {
      const metadataPath = buildDownloadMetadataPath(taskId, 0, membershipStatus);
      const {res, body} = await requestJson(sessionRef, sessionPath, 'GET', metadataPath, 'download');
      const data = unwrap(res, body, 'download metadata');
      signed = data?.downloadUrl ?? null;
      if (typeof signed === 'string' && signed.length > 0) break;
      await new Promise(resolve => setTimeout(resolve, 5000));
    }
    if (!signed) throw new Error('DOWNLOAD_URL_ABSENT');
    if (new URL(signed).protocol !== 'https:') throw new Error('DOWNLOAD_URL_NOT_HTTPS');
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 120000);
    let videoRes;
    try { videoRes = await fetch(signed, {method: 'GET', redirect: 'follow', signal: controller.signal}); }
    finally { clearTimeout(timer); }
    if (!videoRes.ok) throw new Error(`VIDEO_DOWNLOAD_HTTP_${videoRes.status}`);
    const bytes = new Uint8Array(await videoRes.arrayBuffer());
    if (!bytes.byteLength) throw new Error('DOWNLOADED_VIDEO_EMPTY');
    await fsp.writeFile(videoPath, bytes, {mode: 0o600});

    const probe = spawnSync('ffprobe', ['-v','error','-select_streams','v:0','-show_entries','stream=width,height:format=duration','-of','json',videoPath], {encoding:'utf8'});
    if (probe.status !== 0) throw new Error('FFPROBE_VALIDATION_FAILED');
    const parsed = JSON.parse(probe.stdout);
    const width = Number(parsed.streams?.[0]?.width), height = Number(parsed.streams?.[0]?.height), seconds = Number(parsed.format?.duration);
    if (!(width > 0 && height > 0 && seconds > 0)) throw new Error('VIDEO_TECHNICAL_METADATA_INVALID');

    const rel = path.relative(projectRoot, videoPath).split(path.sep).join('/');
    const artifact = {
      schema_version: 1, run_id: task.run_id, task_id: task.task_id, asset_id: task.asset_id,
      status: 'SUCCESS', generation_route: 'happyhorse', execution_route: 'happyhorse', asset_kind: 'video',
      role: task.role, in_content_timeline: Boolean(task.in_content_timeline), prompt_sha256: shaText(task.prompt),
      local_path: rel, sha256: shaFile(videoPath), file_size_bytes: fs.statSync(videoPath).size,
      width, height, duration_ms: Math.round(seconds * 1000), model_identity: 'happyhorse-cli-0.1.9/provider-model-1.5',
      provider_metadata: {
        project_id: projectId, provider_task_id: taskId, project_reuse: false,
        task_status_history: statusHistory, watermarked: membershipStatus?.isMember === true ? false : true,
        aiWater: true, ambiguous_task_submission: false,
      },
      recovery_executor_reconstructed: true, historical_executor_byte_identical: false,
    };
    atomicJson(artifactPath, artifact, 0o600);
    return artifact;
  } catch (e) {
    const code = String(e?.message || 'HAPPYHORSE_EXECUTION_FAILED');
    const artifact = {
      schema_version: 1, run_id: task.run_id, task_id: task.task_id, asset_id: task.asset_id,
      status: 'BLOCK', generation_route: 'happyhorse', execution_route: 'happyhorse', asset_kind: 'video',
      role: task.role, in_content_timeline: Boolean(task.in_content_timeline), prompt_sha256: shaText(task.prompt),
      block_code: code.startsWith('AMBIGUOUS_TASK_SUBMISSION') ? 'AMBIGUOUS_TASK_SUBMISSION' : code,
      provider_metadata: {project_id: projectId, provider_task_id: taskId, project_reuse: false, task_status_history: statusHistory, ambiguous_task_submission: code.startsWith('AMBIGUOUS_TASK_SUBMISSION')},
      recovery_executor_reconstructed: true, historical_executor_byte_identical: false,
    };
    atomicJson(artifactPath, artifact, 0o600);
    throw e;
  }
}

async function main() {
  const args = process.argv.slice(2);
  const validateOnly = args.includes('--validate-only');
  const clean = args.filter(x => x !== '--validate-only');
  const [taskPath, projectRootArg] = clean;
  if (!taskPath) throw new Error('usage: happyhorse-t2v-runner.mjs [--validate-only] <task.json> [project-root]');
  const task = loadJson(path.resolve(taskPath));
  if (validateOnly) {
    const projection = validateTask(task);
    process.stdout.write(JSON.stringify({status:'VALID', prompt_sha256:shaText(task.prompt), projection}, null, 2) + '\n');
    return;
  }
  const projectRoot = path.resolve(projectRootArg || path.join(path.dirname(new URL(import.meta.url).pathname), '../../..'));
  const artifact = await execute(task, projectRoot);
  process.stdout.write(JSON.stringify({status: artifact.status, artifact}, null, 2) + '\n');
}

main().catch(e => { process.stderr.write(`${e.message}\n`); process.exitCode = 2; });
