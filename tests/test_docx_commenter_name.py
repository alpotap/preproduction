import unittest

from lxml import etree

from toolkit.document_processor import _build_comments_xml
from toolkit.runtime_yaml import apply_runtime_yaml_overrides


class DocxCommenterNameTests(unittest.TestCase):
    def test_runtime_yaml_override_applies_docx_commenter_name(self):
        merged = apply_runtime_yaml_overrides(
            {"docx_commenter_name": "AI Reviewer"},
            {
                "runtime": {
                    "docx": {
                        "commenter_name": "Jordan Lee",
                    }
                }
            },
        )
        self.assertEqual("Jordan Lee", merged.get("docx_commenter_name"))

    def test_comments_xml_uses_configured_author_and_initials(self):
        xml_bytes = _build_comments_xml(
            [(0, "Sample comment")],
            config={"docx_commenter_name": "Jordan Lee"},
        )
        root = etree.fromstring(xml_bytes)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        comment = root.xpath("//w:comment", namespaces=namespace)[0]
        self.assertEqual("Jordan Lee", comment.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}author"))
        self.assertEqual("JL", comment.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}initials"))


if __name__ == "__main__":
    unittest.main()
