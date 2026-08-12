import struct
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from volcengine_image_adapter import AdapterError, image_dimensions, load_access_key


class AdapterTests(unittest.TestCase):
    def test_png_dimensions(self):
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 640, 480)
        self.assertEqual(image_dimensions(data), (640, 480))

    def test_credential_labels(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "key.txt"
            p.write_text("Access Key ID: example-ak\nSecret Access Key: example-sk\n")
            self.assertEqual(load_access_key(p), ("example-ak", "example-sk"))

    def test_accesskeyid_labels(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "key.txt"
            p.write_text("AccessKeyId: example-ak\nSecretAccessKey: example-sk\n")
            self.assertEqual(load_access_key(p), ("example-ak", "example-sk"))

    def test_reject_extra_record(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "key.txt"
            p.write_text("AccessKeyID=a\nSecretAccessKey=b\nextra=c\n")
            with self.assertRaises(AdapterError):
                load_access_key(p)

    def test_concurrency_guard_fails_closed_before_network(self):
        from volcengine_image_adapter import VolcengineImageAdapter
        client = VolcengineImageAdapter("ak", "sk")
        client.in_flight = 1
        with self.assertRaises(AdapterError) as ctx:
            client._request("CVSync2AsyncGetResult", {"req_key": "x", "task_id": "y"}, submission=False)
        self.assertEqual(ctx.exception.code, "CONCURRENCY_VIOLATION")


if __name__ == "__main__":
    unittest.main()
