import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from segment_video_master import segment_text, verify_lossless


class SegmenterTests(unittest.TestCase):
    def assert_lossless(self, text):
        segments = segment_text(text)
        self.assertEqual(verify_lossless(text, segments), {
            "segment_reconstruction_match": True,
            "text_loss": False,
            "text_addition": False,
            "text_reorder": False,
        })
        self.assertEqual("".join(x.text for x in segments), text)

    def test_multiple_chinese_paragraphs(self):
        self.assert_lossless("第一句。\n\n第二句？\n第三句！")

    def test_single_sentence(self):
        self.assert_lossless("只有一句。")

    def test_unterminated_tail(self):
        self.assert_lossless("前句。没有终止标点的尾句")

    def test_blank_paragraphs(self):
        self.assert_lossless("甲。\n\n\n乙。\n")

    def test_question_and_exclamation(self):
        self.assert_lossless("真的吗？当然！")

    def test_overlimit_secondary_split(self):
        text = "甲，乙，丙。"
        segments = segment_text(text, max_text_characters=2)
        self.assertEqual("".join(x.text for x in segments), text)


if __name__ == "__main__":
    unittest.main()

