import unittest

from toolkit.web_jobs import _parse_render_cached_selections


class WebJobsRenderCachedSelectionTests(unittest.TestCase):
    def test_parse_render_cached_tokens(self):
        tokens = [
            "cache::default::alpha.docx",
            "cache::paragraph_rewrite::alpha.docx",
            "cache::default::beta.docx",
        ]

        parsed = _parse_render_cached_selections(tokens)

        self.assertEqual(
            [
                ("alpha.docx", "default"),
                ("alpha.docx", "paragraph_rewrite"),
                ("beta.docx", "default"),
            ],
            parsed,
        )

    def test_parse_dedupes_and_ignores_invalid_tokens(self):
        tokens = [
            "cache::default::alpha.docx",
            "cache::default::alpha.docx",
            "invalid",
            "cache::default::",
        ]

        parsed = _parse_render_cached_selections(tokens)

        self.assertEqual([("alpha.docx", "default")], parsed)


if __name__ == "__main__":
    unittest.main()
