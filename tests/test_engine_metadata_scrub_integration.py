import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

from toolkit.docx_metadata import scrub_docx_metadata


class EngineMetadataScrubIntegrationTests(unittest.TestCase):
    def test_scrubbed_docx_removes_app_fingerprint_and_custom_props(self):
        with TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "artifact.docx"
            with ZipFile(target, "w", ZIP_DEFLATED) as archive:
                archive.writestr(
                    "docProps/app.xml",
                    (
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                        '<Application>Microsoft Office Word</Application>'
                        '<Template>Normal.dotm</Template>'
                        '</Properties>'
                    ).encode("utf-8"),
                )
                archive.writestr(
                    "docProps/custom.xml",
                    (
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"/>'
                    ).encode("utf-8"),
                )

            scrub_docx_metadata(target, "AI Reviewer")

            with ZipFile(target, "r") as archive:
                self.assertNotIn("docProps/custom.xml", set(archive.namelist()))
                app_root = etree.fromstring(archive.read("docProps/app.xml"))
                ns = {"ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"}
                self.assertIsNone(app_root.find(".//ep:Application", namespaces=ns))
                self.assertIsNone(app_root.find(".//ep:Template", namespaces=ns))


if __name__ == "__main__":
    unittest.main()
