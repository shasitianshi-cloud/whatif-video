import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from orchestrator import narration_completeness_gate, split_oversized_unit


class NarrationDurationGateTests(unittest.TestCase):
    def test_split_prefers_semicolon_and_reconstructs_parent(self):
        parent = {"segment_id": "seg-003", "text": "甲，乙；丙，丁：戊", "split_depth": 0}
        children = split_oversized_unit(parent)
        self.assertEqual([x["segment_id"] for x in children], ["seg-003a", "seg-003b"])
        self.assertEqual("".join(x["text"] for x in children), parent["text"])
        self.assertEqual(children[0]["parent_segment_id"], "seg-003")
        self.assertEqual(children[0]["split_depth"], 1)
        self.assertTrue(children[0]["text"].endswith("；"))

    def test_recursive_ids_are_stable(self):
        child = split_oversized_unit({"segment_id": "seg-003a", "text": "甲，乙，丙", "split_depth": 1})
        self.assertEqual([x["segment_id"] for x in child], ["seg-003aa", "seg-003ab"])
        self.assertEqual(child[0]["split_depth"], 2)

    def test_depth_limit_stops(self):
        with self.assertRaisesRegex(RuntimeError, "MAX_SPLIT_DEPTH"):
            split_oversized_unit({"segment_id": "seg-003aaa", "text": "甲，乙", "split_depth": 3})

    def test_gate_requires_strictly_less_than_15000(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = Path(tmp)
            (audio_dir / "seg-001.mp3").write_bytes(b"x")
            plan = {"segments": [{"segment_id": "seg-001"}]}
            manifest = {"segments": [{"segment_id": "seg-001", "duration_ms": 15000}]}
            gate = narration_completeness_gate(plan, manifest, audio_dir)
            self.assertEqual(gate["narration_completeness_gate"], "FAIL")
            self.assertFalse(gate["all_audio_duration_ms_lt_15000"])

    def test_superseded_parent_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = Path(tmp)
            for segment_id in ("seg-003", "seg-003a", "seg-003b"):
                (audio_dir / f"{segment_id}.mp3").write_bytes(b"x")
            plan = {"segments": [{"segment_id": "seg-003a"}, {"segment_id": "seg-003b"}]}
            manifest = {"segments": [
                {"segment_id": "seg-003a", "duration_ms": 8000},
                {"segment_id": "seg-003b", "duration_ms": 7000},
            ]}
            gate = narration_completeness_gate(plan, manifest, audio_dir)
            self.assertEqual(gate["actual_audio_segment_ids"], ["seg-003a", "seg-003b"])
            self.assertEqual(gate["narration_completeness_gate"], "PASS")


if __name__ == "__main__":
    unittest.main()
