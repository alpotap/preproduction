import unittest

from toolkit.llm_service import _as_bool, _sanitize_corrections_ai_only


class AiOnlyCorrectionsTests(unittest.TestCase):
    def test_as_bool_parses_supported_values(self):
        self.assertTrue(_as_bool(True))
        self.assertTrue(_as_bool("true"))
        self.assertTrue(_as_bool("YES"))
        self.assertFalse(_as_bool(False))
        self.assertFalse(_as_bool("off"))
        self.assertFalse(_as_bool("0"))

    def test_ai_only_sanitize_preserves_model_entries_without_augmentation(self):
        raw = [
            {
                "explanation": "Model suggestion.",
                "original": "Line without period",
                "corrected": "Line without period.",
            },
            "invalid-entry",
            {
                "explanation": "No explicit corrected value.",
                "original": "Keep original",
            },
            {
                "explanation": "Missing original should be skipped.",
                "original": "",
                "corrected": "ignored",
            },
        ]

        sanitized = _sanitize_corrections_ai_only(raw)

        self.assertEqual(2, len(sanitized))
        self.assertEqual("Line without period.", sanitized[0]["corrected"])
        self.assertEqual("Keep original", sanitized[1]["corrected"])

    def test_ai_only_sanitize_drops_invalid_terminal_punctuation_appends(self):
        raw = [
            {
                "explanation": "Invalid punctuation append.",
                "original": "Did transactions per second increase?",
                "corrected": "Did transactions per second increase?.",
            },
            {
                "explanation": "Invalid punctuation append.",
                "original": "However, performance analysis often requires deeper questions, such as:",
                "corrected": "However, performance analysis often requires deeper questions, such as:.",
            },
            {
                "explanation": "Valid correction.",
                "original": "Missing punctuation",
                "corrected": "Missing punctuation.",
            },
        ]

        sanitized = _sanitize_corrections_ai_only(raw)

        self.assertEqual(1, len(sanitized))
        self.assertEqual("Missing punctuation.", sanitized[0]["corrected"])


if __name__ == "__main__":
    unittest.main()
