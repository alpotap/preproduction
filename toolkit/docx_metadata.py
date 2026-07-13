"""DOCX metadata scrubbing helpers for privacy-safe output artifacts."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_DCTERMS_NS = "http://purl.org/dc/terms/"
_EP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"


def _commenter_initials(name: str) -> str:
    letters = [part[0].upper() for part in str(name or "").split() if part]
    if letters:
        return "".join(letters[:3])
    compact = "".join(ch for ch in str(name or "") if ch.isalpha()).upper()
    return compact[:3] if compact else "AI"


def _remove_nodes(parent, xpath_expr: str, ns: dict) -> bool:
    changed = False
    for node in parent.xpath(xpath_expr, namespaces=ns):
        target_parent = node.getparent()
        if target_parent is not None:
            target_parent.remove(node)
            changed = True
    return changed


def scrub_docx_metadata(docx_path: str | Path, commenter_name: str) -> None:
    """Scrub traceable metadata from a DOCX while keeping commenter identity only."""
    path = Path(docx_path)
    if not path.exists() or path.suffix.lower() != ".docx":
        return

    safe_commenter = str(commenter_name or "AI Reviewer").strip() or "AI Reviewer"
    safe_initials = _commenter_initials(safe_commenter)

    with ZipFile(path, "r") as source_zip:
        file_map = {name: source_zip.read(name) for name in source_zip.namelist()}

    changed_files: set[str] = set()

    # Remove custom document properties entirely.
    if "docProps/custom.xml" in file_map:
        del file_map["docProps/custom.xml"]
        changed_files.add("docProps/custom.xml")

    # Normalize core metadata to commenter identity only.
    core_name = "docProps/core.xml"
    if core_name in file_map:
        try:
            root = etree.fromstring(file_map[core_name])
            ns = {"cp": _CP_NS, "dc": _DC_NS, "dcterms": _DCTERMS_NS}
            creator = root.find(".//dc:creator", namespaces=ns)
            if creator is None:
                creator = etree.SubElement(root, f"{{{_DC_NS}}}creator")
            creator.text = safe_commenter

            last_modified_by = root.find(".//cp:lastModifiedBy", namespaces=ns)
            if last_modified_by is None:
                last_modified_by = etree.SubElement(root, f"{{{_CP_NS}}}lastModifiedBy")
            last_modified_by.text = safe_commenter

            _remove_nodes(root, ".//dc:title", ns)
            _remove_nodes(root, ".//dc:subject", ns)
            _remove_nodes(root, ".//dc:description", ns)
            _remove_nodes(root, ".//cp:keywords", ns)
            _remove_nodes(root, ".//cp:category", ns)
            _remove_nodes(root, ".//cp:contentStatus", ns)
            _remove_nodes(root, ".//dcterms:created", ns)
            _remove_nodes(root, ".//dcterms:modified", ns)

            file_map[core_name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            changed_files.add(core_name)
        except Exception:
            pass

    # Remove app metadata that can fingerprint environment/tooling.
    app_name = "docProps/app.xml"
    if app_name in file_map:
        try:
            root = etree.fromstring(file_map[app_name])
            ns = {"ep": _EP_NS}
            _remove_nodes(root, ".//ep:Application", ns)
            _remove_nodes(root, ".//ep:AppVersion", ns)
            _remove_nodes(root, ".//ep:Company", ns)
            _remove_nodes(root, ".//ep:Manager", ns)
            _remove_nodes(root, ".//ep:Template", ns)
            _remove_nodes(root, ".//ep:HyperlinkBase", ns)

            file_map[app_name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            changed_files.add(app_name)
        except Exception:
            pass

    # Normalize all revision/comment authors in word XML parts.
    author_attr = f"{{{_W_NS}}}author"
    initials_attr = f"{{{_W_NS}}}initials"
    for name, content in list(file_map.items()):
        if not (name.startswith("word/") and name.endswith(".xml")):
            continue
        try:
            root = etree.fromstring(content)
        except Exception:
            continue

        changed = False
        for element in root.iter():
            if author_attr in element.attrib and element.attrib.get(author_attr) != safe_commenter:
                element.attrib[author_attr] = safe_commenter
                changed = True
            if name == "word/comments.xml" and initials_attr in element.attrib:
                if element.attrib.get(initials_attr) != safe_initials:
                    element.attrib[initials_attr] = safe_initials
                    changed = True

        if changed:
            file_map[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            changed_files.add(name)

    if not changed_files:
        return

    with ZipFile(path, "w", ZIP_DEFLATED) as target_zip:
        for name, content in file_map.items():
            target_zip.writestr(name, content)
