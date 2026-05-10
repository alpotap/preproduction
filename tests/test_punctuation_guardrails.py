import unittest

from toolkit.document_processor import _filter_corrections_for_block
from toolkit.llm_service import _sanitize_and_augment_corrections


class PunctuationGuardrailTests(unittest.TestCase):
    def test_augmentation_skips_semantically_duplicate_missing_period_fix(self):
        result = [
            {
                "explanation": "Missing sentence-ending period in list item.",
                "original": "- List item",
                "corrected": "- List item.",
            }
        ]
        text = "- List item\n- Another list item"

        sanitized, _, added_missing_period_entries, _ = _sanitize_and_augment_corrections(result, text)

        self.assertEqual(2, len(sanitized))
        self.assertEqual(1, added_missing_period_entries)
        self.assertIn(
            {
                "explanation": "Missing sentence-ending period in list item.",
                "original": "- Another list item",
                "corrected": "- Another list item.",
            },
            sanitized,
        )

    def test_augmentation_does_not_generate_double_terminal_period(self):
        result = [
            {
                "explanation": "Missing sentence-ending period in list item.",
                "original": "1. Already punctuated item",
                "corrected": "1. Already punctuated item.",
            }
        ]
        text = "1. Already punctuated item\n2. Needs punctuation"

        sanitized, _, _, _ = _sanitize_and_augment_corrections(result, text)

        generated = [entry for entry in sanitized if entry["original"] == "2. Needs punctuation"]
        self.assertEqual(1, len(generated))
        self.assertEqual("2. Needs punctuation.", generated[0]["corrected"])
        self.assertFalse(generated[0]["corrected"].endswith(".."))

    def test_filter_skips_correction_when_boundary_already_has_period(self):
        block_content = "Programming languages are used in many fields."
        corrections = [
            {
                "explanation": "Missing period.",
                "original": "many fields",
                "corrected": "many fields.",
            }
        ]

        block_corrections = _filter_corrections_for_block(block_content, corrections)

        self.assertEqual([], block_corrections)

    def test_filter_keeps_period_fix_when_boundary_has_no_period(self):
        block_content = "Programming languages are used in many fields"
        corrections = [
            {
                "explanation": "Missing period.",
                "original": "many fields",
                "corrected": "many fields.",
            }
        ]

        block_corrections = _filter_corrections_for_block(block_content, corrections)

        self.assertEqual(1, len(block_corrections))
        self.assertEqual("s", block_corrections[0]["original"])
        self.assertEqual("s.", block_corrections[0]["corrected"])


if __name__ == "__main__":
    unittest.main()
