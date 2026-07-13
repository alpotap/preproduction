import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from toolkit.engine import _save_correction_plan_cache, _load_correction_plan_cache


class EngineCacheTests(unittest.TestCase):
    def test_save_and_load_correction_plan_cache(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = root / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            source_file = root / "sample.docx"
            source_file.write_bytes(b"sample content")

            correction_plan = [{"content": "Hello world", "corrections": []}]
            summary = {"correctionCount": 0, "categoryCounts": {}}

            cache_path = _save_correction_plan_cache(
                output_dir,
                "default",
                source_file,
                "docx",
                correction_plan,
                summary,
            )
            self.assertTrue(cache_path.exists())

            payload, error = _load_correction_plan_cache(output_dir, "default", source_file)
            self.assertIsNone(error)
            self.assertIsInstance(payload, dict)
            self.assertEqual("default", payload.get("promptKey"))
            self.assertEqual("sample.docx", payload.get("sourceFileName"))
            self.assertEqual(correction_plan, payload.get("correctionPlan"))

    def test_cache_rejected_when_source_changes(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = root / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            source_file = root / "sample.docx"
            source_file.write_bytes(b"sample content")

            correction_plan = [{"content": "Hello world", "corrections": []}]
            summary = {"correctionCount": 0, "categoryCounts": {}}

            _save_correction_plan_cache(
                output_dir,
                "default",
                source_file,
                "docx",
                correction_plan,
                summary,
            )

            source_file.write_bytes(b"changed content")

            payload, error = _load_correction_plan_cache(output_dir, "default", source_file)
            self.assertIsNone(payload)
            self.assertIsInstance(error, str)
            self.assertIn("stale", error.lower())


if __name__ == "__main__":
    unittest.main()
