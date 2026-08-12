from __future__ import annotations

import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "video-production" / "src"
sys.path.insert(0, str(SRC))

from run_asset_executor import advance  # noqa: E402
from volcengine_image_adapter import CallResult  # noqa: E402
from volcengine_image_execution import EXECUTION_ADAPTER  # noqa: E402

RUN_ID = "volcengine-image-serial-9task-regression-v2"
RUN_ROOT = ROOT / "runs" / RUN_ID


def fake_png(width: int = 1280, height: int = 720) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", width, height) + b"fixture"


class FakeSerialAdapter:
    def __init__(self):
        self.calls = 0
        self.in_flight = 0
        self.max_in_flight = 0
        self.requested_dimensions = []

    def generate(self, prompt: str, *, width: int, height: int, poll_interval: int, max_polls: int):
        assert prompt
        assert self.in_flight == 0
        assert width == 1280
        assert height == 720
        assert poll_interval == 3
        assert max_polls == 100
        self.requested_dimensions.append((width, height))
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            self.calls += 1
            return CallResult(
                task_id=f"provider-task-{self.calls}",
                request_id=f"provider-request-{self.calls}",
                image_bytes=fake_png(width, height),
                redacted_response={"code": 10000, "data": {"status": "done", "image_count": 1}},
            )
        finally:
            self.in_flight -= 1


def build_dispatch():
    tasks = []
    for i in range(9):
        aid = f"img-{i+1:03d}"
        tasks.append({
            "task_id": f"dispatch-{aid}",
            "run_id": RUN_ID,
            "asset_id": aid,
            "role": "content_visual" if i < 8 else "cover",
            "generation_route": "gpt-image-2",
            "expected_asset_kind": "image",
            "prompt": f"exact prompt {i+1}",
            "in_content_timeline": i < 8,
        })
    return {"schema_version": 1, "run_id": RUN_ID, "tasks": tasks}


def main():
    shutil.rmtree(RUN_ROOT, ignore_errors=True)
    try:
        dispatch = build_dispatch()
        pending = advance(dispatch, execute_provider=False, image_execution_adapter=EXECUTION_ADAPTER)
        assert pending["status"] == "PROVIDER_EXECUTION_REQUIRED"
        assert pending["next_task_index"] == 0
        assert pending["image_execution_adapter"] == EXECUTION_ADAPTER

        shutil.rmtree(RUN_ROOT, ignore_errors=True)
        fake = FakeSerialAdapter()
        result = advance(
            dispatch,
            execute_provider=True,
            image_execution_adapter=EXECUTION_ADAPTER,
            image_adapter=fake,
        )
        assert result["status"] == "COMPLETE"
        assert result["next_task_index"] == 9
        assert fake.calls == 9
        assert fake.max_in_flight == 1
        assert fake.requested_dimensions == [(1280, 720)] * 9
        assert result["completeness"]["dispatch_task_count"] == 9
        assert result["completeness"]["success_task_count"] == 9
        assert result["completeness"]["asset_execution_completeness_pass"] is True
        print("TASK_COUNT=9")
        print("SUCCESS_COUNT=9")
        print("MAX_IN_FLIGHT_REQUESTS=1")
        print("REQUESTED_IMAGE_WIDTH=1280")
        print("REQUESTED_IMAGE_HEIGHT=720")
        print("SERIAL_EXECUTION=true")
        print("AUTO_CONTINUE_AFTER_SUCCESS=true")
        print("HOST_INTERACTION_REQUIRED=false")
        print("SERIAL_9_TASK_MOCK_PASS=true")
    finally:
        shutil.rmtree(RUN_ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
