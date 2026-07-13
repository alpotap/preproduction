import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

from toolkit.docx_metadata import scrub_docx_metadata


_CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_EP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class DocxMetadataScrubberTests(unittest.TestCase):
    def test_scrubber_keeps_commenter_identity_and_removes_traceable_metadata(self):
        with TemporaryDirectory() as tmp_dir:
            docx_path = Path(tmp_dir) / "sample.docx"

            core_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:dcterms="http://purl.org/dc/terms/">'
                '<dc:title>Secret title</dc:title>'
                '<dc:creator>Original User</dc:creator>'
                '<cp:lastModifiedBy>Original User</cp:lastModifiedBy>'
                '</cp:coreProperties>'
            ).encode("utf-8")

            app_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                '<Application>Microsoft Office Word</Application>'
                '<AppVersion>16.0000</AppVersion>'
                '<Template>Normal.dotm</Template>'
                '</Properties>'
            ).encode("utf-8")

            document_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body><w:p><w:ins w:id="1" w:author="Original User"><w:r><w:t>x</w:t></w:r></w:ins></w:p></w:body>'
                '</w:document>'
            ).encode("utf-8")

            comments_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:comment w:id="0" w:author="Original User" w:initials="OU"><w:p><w:r><w:t>x</w:t></w:r></w:p></w:comment>'
                '</w:comments>'
            ).encode("utf-8")

            custom_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
                'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
                '<property pid="2" name="MachineId" fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}">'
                '<vt:lpwstr>ABC</vt:lpwstr></property>'
                '</Properties>'
            ).encode("utf-8")

            with ZipFile(docx_path, "w", ZIP_DEFLATED) as archive:
                archive.writestr("docProps/core.xml", core_xml)
                archive.writestr("docProps/app.xml", app_xml)
                archive.writestr("docProps/custom.xml", custom_xml)
                archive.writestr("word/document.xml", document_xml)
                archive.writestr("word/comments.xml", comments_xml)

            scrub_docx_metadata(docx_path, "Jordan Lee")

            with ZipFile(docx_path, "r") as archive:
                names = set(archive.namelist())
                self.assertNotIn("docProps/custom.xml", names)

                core_root = etree.fromstring(archive.read("docProps/core.xml"))
                ns_core = {"cp": _CP_NS, "dc": _DC_NS}
                creator = core_root.find(".//dc:creator", namespaces=ns_core)
                last_mod = core_root.find(".//cp:lastModifiedBy", namespaces=ns_core)
                title = core_root.find(".//dc:title", namespaces=ns_core)
                self.assertEqual("Jordan Lee", (creator.text or "").strip())
                self.assertEqual("Jordan Lee", (last_mod.text or "").strip())
                self.assertIsNone(title)

                app_root = etree.fromstring(archive.read("docProps/app.xml"))
                ns_app = {"ep": _EP_NS}
                self.assertIsNone(app_root.find(".//ep:Application", namespaces=ns_app))
                self.assertIsNone(app_root.find(".//ep:AppVersion", namespaces=ns_app))
                self.assertIsNone(app_root.find(".//ep:Template", namespaces=ns_app))

                doc_root = etree.fromstring(archive.read("word/document.xml"))
                ns_w = {"w": _W_NS}
                ins = doc_root.xpath("//w:ins", namespaces=ns_w)[0]
                self.assertEqual("Jordan Lee", ins.get(f"{{{_W_NS}}}author"))

                comments_root = etree.fromstring(archive.read("word/comments.xml"))
                comment = comments_root.xpath("//w:comment", namespaces=ns_w)[0]
                self.assertEqual("Jordan Lee", comment.get(f"{{{_W_NS}}}author"))
                self.assertEqual("JL", comment.get(f"{{{_W_NS}}}initials"))


if __name__ == "__main__":
    unittest.main()
