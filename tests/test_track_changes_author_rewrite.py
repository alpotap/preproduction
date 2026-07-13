import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from lxml import etree

from toolkit.tracked_processor import _normalize_track_changes_authors


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class TrackChangesAuthorRewriteTests(unittest.TestCase):
    def test_normalize_rewrites_revision_and_comment_authors(self):
        with TemporaryDirectory() as tmp_dir:
            docx_path = Path(tmp_dir) / "sample.docx"
            document_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body><w:p><w:r><w:t>Base</w:t></w:r>'
                '<w:ins w:id="1" w:author="Old Name" w:date="2026-01-01T00:00:00Z">'
                '<w:r><w:t> Added</w:t></w:r></w:ins>'
                '</w:p></w:body></w:document>'
            ).encode("utf-8")
            comments_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:comment w:id="0" w:author="Old Name" w:initials="ON">'
                '<w:p><w:r><w:t>Comment</w:t></w:r></w:p>'
                '</w:comment></w:comments>'
            ).encode("utf-8")

            with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("word/document.xml", document_xml)
                archive.writestr("word/comments.xml", comments_xml)

            _normalize_track_changes_authors(str(docx_path), "Jordan Lee", "JL")

            with zipfile.ZipFile(docx_path, "r") as archive:
                updated_document = etree.fromstring(archive.read("word/document.xml"))
                updated_comments = etree.fromstring(archive.read("word/comments.xml"))

            ns = {"w": _W_NS}
            ins = updated_document.xpath("//w:ins", namespaces=ns)[0]
            comment = updated_comments.xpath("//w:comment", namespaces=ns)[0]

            self.assertEqual("Jordan Lee", ins.get(f"{{{_W_NS}}}author"))
            self.assertEqual("Jordan Lee", comment.get(f"{{{_W_NS}}}author"))
            self.assertEqual("JL", comment.get(f"{{{_W_NS}}}initials"))


if __name__ == "__main__":
    unittest.main()
