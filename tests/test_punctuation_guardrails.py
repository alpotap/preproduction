import unittest

from toolkit.document_processor import _filter_corrections_for_block
from toolkit.llm_service import (
    _sanitize_and_augment_corrections,
    _sanitize_corrections_ai_only,
)


class PunctuationGuardrailTests(unittest.TestCase):
    def test_sanitize_swaps_missing_comma_correction_when_direction_is_reversed(self):
        result = [
            {
                "explanation": "Missing comma after introductory phrase.",
                "original": "By this time, my",
                "corrected": "By this time my",
            }
        ]

        sanitized = _sanitize_corrections_ai_only(result)

        self.assertEqual(1, len(sanitized))
        self.assertEqual("By this time my", sanitized[0]["original"])
        self.assertEqual("By this time, my", sanitized[0]["corrected"])

    def test_sanitize_swaps_unnecessary_comma_correction_when_direction_is_reversed(self):
        result = [
            {
                "explanation": "Unnecessary comma before 'she'.",
                "original": "Another surprise was she",
                "corrected": "Another surprise was, she",
            }
        ]

        sanitized = _sanitize_corrections_ai_only(result)

        self.assertEqual(1, len(sanitized))
        self.assertEqual("Another surprise was, she", sanitized[0]["original"])
        self.assertEqual("Another surprise was she", sanitized[0]["corrected"])

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

    def test_filter_skips_ambiguous_single_comma_correction(self):
        block_content = "By this time, my wife was ready, and everyone knew."
        corrections = [
            {
                "explanation": "Unnecessary comma.",
                "original": ",",
                "corrected": "",
            }
        ]

        block_corrections = _filter_corrections_for_block(block_content, corrections)
        self.assertEqual([], block_corrections)


    # --- mid-sentence period guard ---

    def test_sanitize_drops_correction_with_period_before_lowercase(self):
        """LLM output that inserts '. [lowercase]' (e.g., 'typically. organized') is dropped."""
        result = [
            {
                "explanation": "Sentence should end here.",
                "original": "The output is typically organized into",
                "corrected": "The output is typically. organized into",
            }
        ]
        sanitized = _sanitize_corrections_ai_only(result)
        self.assertEqual([], sanitized)

    def test_sanitize_drops_mid_sentence_split_with_period_lowercase(self):
        """Period inserted before a lowercase continuation is rejected (Examples 1, 2 from bug report)."""
        result = [
            {
                "explanation": "Added period.",
                "original": "peak load focuses",
                "corrected": "peak load. focuses",
            }
        ]
        sanitized = _sanitize_corrections_ai_only(result)
        self.assertEqual([], sanitized)

    def test_sanitize_keeps_valid_period_before_uppercase(self):
        """A correction that properly ends a sentence with '. Capital' is not dropped."""
        result = [
            {
                "explanation": "Split run-on.",
                "original": "end start",
                "corrected": "end. Start",
            }
        ]
        sanitized = _sanitize_corrections_ai_only(result)
        self.assertEqual(1, len(sanitized))

    def test_sanitize_augment_drops_period_before_lowercase(self):
        """_sanitize_and_augment_corrections also rejects mid-sentence period insertions."""
        result = [
            {
                "explanation": "Wrong split.",
                "original": "trends topic",
                "corrected": "trends. topic",
            }
        ]
        sanitized, dropped, _, _ = _sanitize_and_augment_corrections(result, "trends topic")
        self.assertEqual([], sanitized)
        self.assertEqual(1, dropped)

    # --- period-before-comma guard ---

    def test_filter_drops_period_that_would_precede_comma(self):
        """A correction that ends with '.' must be rejected when the next character is ','."""
        block_content = "throughput dropped disproportionately, indicating inefficiencies."
        corrections = [
            {
                "explanation": "Added period.",
                "original": "disproportionately",
                "corrected": "disproportionately.",
            }
        ]
        block_corrections = _filter_corrections_for_block(block_content, corrections)
        self.assertEqual([], block_corrections)

    def test_filter_keeps_period_when_next_char_is_not_comma(self):
        """A correction that ends with '.' is kept when no comma follows."""
        block_content = "The run ended successfully"
        corrections = [
            {
                "explanation": "Missing terminal period.",
                "original": "successfully",
                "corrected": "successfully.",
            }
        ]
        block_corrections = _filter_corrections_for_block(block_content, corrections)
        self.assertEqual(1, len(block_corrections))

    def test_sanitize_drops_correction_with_period_before_colon(self):
        """LLM output that inserts '.:' is rejected."""
        result = [
            {
                "explanation": "Added period.",
                "original": "The output is typically:",
                "corrected": "The output is typically.:",
            }
        ]
        sanitized = _sanitize_corrections_ai_only(result)
        self.assertEqual([], sanitized)

    def test_filter_drops_period_that_would_precede_colon(self):
        """A correction that ends with '.' must be rejected when the next character is ':'."""
        block_content = "Top Error Codes by Occurrence: A ranked list"
        corrections = [
            {
                "explanation": "Added period.",
                "original": "Occurrence",
                "corrected": "Occurrence.",
            }
        ]
        block_corrections = _filter_corrections_for_block(block_content, corrections)
        self.assertEqual([], block_corrections)


if __name__ == "__main__":
    unittest.main()
