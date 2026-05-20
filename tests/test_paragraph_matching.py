import unittest

from toolkit.document_processor import _normalize_for_matching


class ParagraphMatchingTests(unittest.TestCase):
    def test_normalize_for_matching_aligns_hidden_whitespace(self):
        plan_text = "Next investigation step Usually recommends checking detailed logs to identify the exact failure message"
        paragraph_with_hidden_ws = "Next\u00a0investigation step Usually recommends checking detailed logs to identify the exact failure message"

        self.assertEqual(plan_text, _normalize_for_matching(paragraph_with_hidden_ws))

    def test_normalize_for_matching_removes_zero_width_chars(self):
        clean = "Aviator usage"
        with_zero_width = "Aviator\u200busage"

        self.assertEqual(clean, _normalize_for_matching(with_zero_width))


if __name__ == "__main__":
    unittest.main()
