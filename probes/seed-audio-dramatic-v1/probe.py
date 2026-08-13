from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

CREATE_URL = "https://openspeech.bytedance.com/api/v3/tts/create"

# Small candidate set only. The probe validates each candidate against the real
# Seed Audio create endpoint and keeps at most two working speakers.
CANDIDATE_SPEAKERS = [
    "zh_female_vv_uranus_bigtts",
    "zh_male_beijingxiaoye_emo_v2_mars_bigtts",
    "zh_female_roumeinvyou_emo_v2_mars_bigtts",
]


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_audio(payload: dict) -> tuple[bytes, object]:
    audio_b64 = payload.get("audio")
    duration = payload.get("original_duration")
    if not isinstance(audio_b64, str) and isinstance(payload.get("data"), dict):
        audio_b64 = payload["data"].get("audio")
        duration = payload["data"].get("original_duration", duration)
    if not isinstance(audio_b64, str) or not audio_b64:
        raise RuntimeError("CREATE_RESPONSE_AUDIO_NOT_FOUND")
    audio = base64.b64decode(audio_b64)
    if not audio:
        raise RuntimeError("CREATE_RESPONSE_AUDIO_EMPTY")
    return audio, duration


def create_audio(api_key: str, prompt: str, speakers: list[str], audio_path: Path, response_path: Path) -> dict:
    body = {
        "model": "seed-audio-1.0",
        "text_prompt": prompt,
        "references": [{"speaker": s} for s in speakers],
        "audio_config": {
            "format": "mp3",
            "sample_rate": 48000,
            "pitch_rate": 0,
            "speech_rate": 0,
            "loudness_rate": 0,
        },
        "watermark": {},
    }
    req = urllib.request.Request(
        CREATE_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "X-Api-Key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read()
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        response_path.parent.mkdir(parents=True, exist_ok=True)
        response_path.write_text(raw.decode("utf-8", "replace"), encoding="utf-8")
        raise RuntimeError(f"CREATE_HTTP_{exc.code}: {raw.decode('utf-8', 'replace')[:500]}") from None

    payload = json.loads(raw.decode("utf-8"))
    save_json(response_path, {"http_status": status, "payload": payload})
    audio, duration = extract_audio(payload)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(audio)
    return {
        "status": "PASS",
        "audio_path": audio_path.as_posix(),
        "audio_sha256": hashlib.sha256(audio).hexdigest(),
        "audio_bytes": len(audio),
        "original_duration": duration,
    }


def validate_speakers(api_key: str, root: Path) -> list[str]:
    selected: list[str] = []
    validations = []
    prompt = "角色1用自然平静的中文说：‘你好，这是一次很短的声音测试。’不要音乐，不要环境音。"
    for index, speaker in enumerate(CANDIDATE_SPEAKERS, start=1):
        try:
            result = create_audio(
                api_key,
                prompt,
                [speaker],
                root / "speaker-validation" / f"speaker-{index:02d}.mp3",
                root / "responses" / f"speaker-validation-{index:02d}.json",
            )
            validations.append({"speaker_id": speaker, "status": "PASS", "result": result})
            selected.append(speaker)
        except Exception as exc:
            validations.append({"speaker_id": speaker, "status": "FAIL", "error": str(exc)})
        if len(selected) >= 2:
            break
    save_json(root / "speaker-validation.json", {"candidates": validations, "selected": selected})
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=Path("probes/seed-audio-dramatic-v1/output"))
    args = parser.parse_args()

    api_key = os.environ.get("VOLCENGINE_TTS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("VOLCENGINE_TTS_API_KEY_MISSING")

    root = args.output_root
    root.mkdir(parents=True, exist_ok=True)
    selected = validate_speakers(api_key, root)
    if not selected:
        save_json(root / "probe-summary.json", {
            "real_api_called": True,
            "create_api_pass": False,
            "speaker_count_selected": 0,
            "block_code": "NO_COMPATIBLE_SPEAKER",
        })
        raise RuntimeError("NO_COMPATIBLE_SPEAKER")

    speaker_binding = [
        {"order": i + 1, "speaker_id": s, "assigned_role": f"角色{i + 1}"}
        for i, s in enumerate(selected)
    ]
    save_json(root / "speaker-discovery.json", {
        "provider_has_list_speakers_api": True,
        "list_speakers_requires_separate_hmac_credentials": True,
        "list_speakers_attempted": False,
        "selection_method": "real_create_endpoint_candidate_validation",
        "selected_speakers": speaker_binding,
    })

    refs_one = [selected[0]]
    refs_dialogue = selected[:2] if len(selected) >= 2 else [selected[0]]
    prompts = {
        "test-a-single": "角色1（年轻说话者，声音自然，不要播音腔）先轻松地说：‘你回来啦。’短暂停顿后突然注意到异常，语气迅速变得紧张和担心：‘等等……你手上的血是怎么回事？’不要背景音乐，不要额外人物，重点表现轻松到紧张的明显情绪转折。",
        "test-b-dialogue": "安静的室内，没有背景音乐。角色1带着压抑的不满问：‘你今天为什么一直躲着我？’角色2明显回避问题，轻声回答：‘没有，我只是有点累。’角色1沉默片刻，语气变得更直接：‘那你看着我说。’角色2沉默，没有回答。角色1的语气从期待转为失望，轻声说道：‘果然。’对白之间保留自然停顿，重点表现人物之间真实的情绪关系和接话节奏。",
        "test-c-scene": "夜晚，下着小雨。室内很安静，窗外能听见轻微雨声。角色1坐在窗边，声音很轻，有明显疲惫感：‘其实我今天一直在等你。’角色2站在不远处，沉默片刻后低声说道：‘对不起。’角色1没有立刻回应。雨声稍微明显了一些。几秒后，角色1平静但明显失望地说道：‘你每次都是这句话。’不要加入音乐，保留真实停顿、雨声和空间感。",
    }
    save_json(root / "prompts.json", prompts)

    results = {}
    for test_id, prompt in prompts.items():
        refs = refs_one if test_id == "test-a-single" else refs_dialogue
        result = create_audio(
            api_key,
            prompt,
            refs,
            root / "audio" / f"{test_id}.mp3",
            root / "responses" / f"{test_id}.json",
        )
        result["references"] = refs
        results[test_id] = result

    summary = {
        "schema_version": 1,
        "real_api_called": True,
        "create_api_pass": True,
        "speaker_discovery_supported": True,
        "speaker_discovery_transport_attempted": False,
        "speaker_count_selected": len(selected),
        "role_speaker_order_binding": speaker_binding,
        "test_a_pass": results["test-a-single"]["status"] == "PASS",
        "test_b_pass": results["test-b-dialogue"]["status"] == "PASS",
        "test_c_pass": results["test-c-scene"]["status"] == "PASS",
        "results": results,
        "credential_values_persisted": False,
    }
    save_json(root / "probe-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
