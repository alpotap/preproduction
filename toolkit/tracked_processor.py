"""Applies shared correction plans to DOCX files using Microsoft Word Track Changes."""

import difflib
import zipfile
import pythoncom
import win32com.client as win32
from lxml import etree

from toolkit.document_processor import build_correction_plan
from toolkit.document_processor import _normalize_for_matching
from toolkit.document_processor import _filter_comment_explanation
from toolkit.utils import build_text_match_index, find_indexed_text_match
from toolkit.docx_metadata import scrub_docx_metadata


WD_FIND_STOP = 0
MAX_FIND_TEXT_LENGTH = 240
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _clean_paragraph_text(text):
    """Normalize Word paragraph text for LLM processing and matching."""
    if not text:
        return ""
    # \x01 appears in Word COM text for inline shapes; \r/\x07 are paragraph/cell end markers.
    return text.replace("\r", "").replace("\x07", "").replace("\x01", "").strip()


def _trim_paragraph_end_markers(text):
    """Remove trailing Word paragraph/cell markers for index-based matching."""
    if not text:
        return ""
    while text.endswith("\r") or text.endswith("\x07"):
        text = text[:-1]
    return text


def _clean_to_raw_index(raw_text, clean_index):
    """Map an index from clean_text (without \x01) back to raw Word text offset."""
    if clean_index <= 0:
        return 0
    raw_idx = 0
    clean_count = 0
    while clean_count < clean_index and raw_idx < len(raw_text):
        if raw_text[raw_idx] != "\x01":
            clean_count += 1
        raw_idx += 1
    return raw_idx


def _find_all_indices(text, needle):
    """Return start indices of all non-overlapping needle matches in text."""
    indices = []
    if not needle:
        return indices
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx == -1:
            break
        indices.append(idx)
        start = idx + max(1, len(needle))
    return indices


def _locate_target_range(word_doc, paragraph, original, preferred_start_clean=None):
    """Locate a Word range for original text using optional clean-text offset guidance."""
    raw_para_text = _trim_paragraph_end_markers(paragraph.Range.Text)
    clean_text = raw_para_text.replace("\x01", "")

    if preferred_start_clean is not None and preferred_start_clean >= 0:
        candidate_indices = _find_all_indices(clean_text, original)
        if candidate_indices:
            if preferred_start_clean in candidate_indices:
                chosen_start = preferred_start_clean
            else:
                later = [i for i in candidate_indices if i >= preferred_start_clean]
                chosen_start = later[0] if later else candidate_indices[-1]

            raw_start = _clean_to_raw_index(raw_para_text, chosen_start)
            base_start = paragraph.Range.Start
            return word_doc.Range(
                Start=base_start + raw_start,
                End=base_start + raw_start + len(original),
            )

    start_idx_clean = clean_text.find(original)
    if start_idx_clean == -1:
        return None

    raw_start = _clean_to_raw_index(raw_para_text, start_idx_clean)
    base_start = paragraph.Range.Start
    return word_doc.Range(
        Start=base_start + raw_start,
        End=base_start + raw_start + len(original),
    )


# wdWithInTable COM constant — True when a range sits inside a table cell.
_WD_WITH_IN_TABLE = 13


def _collect_all_paragraphs_from_docx(doc):
    """Collect paragraphs in body-first order matching python-docx's _collect_all_paragraphs.

    Word COM's doc.Paragraphs returns every paragraph in document-flow order
    (body and table cells interleaved), which differs from python-docx where
    doc.paragraphs yields only top-level body paragraphs.  The correction plan
    is built with python-docx (body first, table cells appended), so we must
    reproduce that ordering here to keep the paragraph cursor in sync.
    """
    body_paragraphs = []
    table_paragraphs = []
    for para in doc.Paragraphs:
        try:
            in_table = para.Range.Information(_WD_WITH_IN_TABLE)
        except Exception:
            in_table = False
        if in_table:
            table_paragraphs.append(para)
        else:
            body_paragraphs.append(para)
    return body_paragraphs + table_paragraphs


def _apply_diff_to_range(word_doc, target_range, original, corrected):
    """Apply minimal tracked edits to a Word range using a character diff."""
    base_start = target_range.Start
    matcher = difflib.SequenceMatcher(None, original, corrected)

    for tag, i1, i2, j1, j2 in reversed(matcher.get_opcodes()):
        if tag == "equal":
            continue

        edit_start = base_start + i1
        edit_end = base_start + i2
        replacement_text = corrected[j1:j2]

        if tag == "insert":
            edit_range = word_doc.Range(Start=edit_start, End=edit_start)
            edit_range.Text = replacement_text
            continue

        edit_range = word_doc.Range(Start=edit_start, End=edit_end)
        edit_range.Text = replacement_text


def _apply_correction_to_paragraph(
    word_doc,
    paragraph,
    original,
    corrected,
    explanation,
    add_comments,
    notify_terminal_punctuation,
    preferred_start_clean=None,
):
    """Apply one correction to a Word paragraph with Track Changes enabled."""
    if not original:
        return False

    para_range = paragraph.Range.Duplicate
    if para_range.End > para_range.Start:
        para_range.End = para_range.End - 1

    target = None

    # Prefer position-aware anchoring from the original paragraph content.
    target = _locate_target_range(word_doc, paragraph, original, preferred_start_clean)

    if target is None and len(original) <= MAX_FIND_TEXT_LENGTH:
        try:
            find = para_range.Find
            find.ClearFormatting()
            find.Text = original
            find.Forward = True
            find.Wrap = WD_FIND_STOP
            if find.Execute():
                target = para_range.Duplicate
        except Exception:
            target = None

    if target is None:
        return False

    filtered_explanation = _filter_comment_explanation(
        explanation,
        {"notify_terminal_punctuation": notify_terminal_punctuation},
    ).strip()

    if add_comments and filtered_explanation:
        try:
            word_doc.Comments.Add(Range=target, Text=filtered_explanation)
        except Exception:
            pass

    _apply_diff_to_range(word_doc, target, original, corrected)
    return True


def _normalize_track_changes_authors(docx_path, commenter_name, commenter_initials):
    """Rewrite author/initials fields in WordprocessingML to configured commenter identity."""
    with zipfile.ZipFile(docx_path, "r") as source_zip:
        file_map = {name: source_zip.read(name) for name in source_zip.namelist()}

    changed_files: set[str] = set()
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
            if author_attr in element.attrib and element.attrib.get(author_attr) != commenter_name:
                element.attrib[author_attr] = commenter_name
                changed = True
            if name == "word/comments.xml" and initials_attr in element.attrib:
                if element.attrib.get(initials_attr) != commenter_initials:
                    element.attrib[initials_attr] = commenter_initials
                    changed = True

        if changed:
            file_map[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            changed_files.add(name)

    if not changed_files:
        return

    with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as target_zip:
        for name, content in file_map.items():
            target_zip.writestr(name, content)


def process_docx_tracked_with_plan(input_path, output_path, correction_plan, config):
    """Apply a precomputed correction plan to a DOCX using Track Changes and comments."""
    print(f"Loading document with Track Changes mode: {input_path}")

    pythoncom.CoInitialize()
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    doc = None
    commenter_name = str(config.get("docx_commenter_name", "AI Reviewer") or "AI Reviewer").strip()
    commenter_initials = ''.join(part[0].upper() for part in commenter_name.split() if part)[:3] or 'AI'

    def _apply_word_author_identity(target_word, target_doc=None):
        try:
            target_word.UserName = commenter_name
            target_word.UserInitials = commenter_initials
        except Exception:
            pass
        if target_doc is None:
            return
        try:
            target_doc.BuiltInDocumentProperties("Author").Value = commenter_name
        except Exception:
            pass
        try:
            target_doc.BuiltInDocumentProperties("Last Author").Value = commenter_name
        except Exception:
            pass

    try:
        _apply_word_author_identity(word)

        doc = word.Documents.Open(input_path)
        _apply_word_author_identity(word, doc)
        doc.TrackRevisions = True

        word_paragraphs = _collect_all_paragraphs_from_docx(doc)
        paragraphs = []
        for para in word_paragraphs:
            text = _clean_paragraph_text(para.Range.Text)
            if text:
                paragraphs.append(
                    {
                        "para": para,
                        "content": text,
                        "normalized_content": _normalize_for_matching(text).strip(),
                    }
                )

        print("Applying tracked changes from shared correction plan...")

        paragraph_cursor = 0
        paragraph_index = build_text_match_index(paragraphs)
        for item in correction_plan:
            block_corrections = item.get("corrections", [])
            if not block_corrections:
                continue

            # item["content"] is python-docx para.text (unstripped); paragraphs[]
            # content is already stripped by _clean_paragraph_text — normalise before comparing.
            item_content_clean = item["content"].strip()
            item_content_normalized = _normalize_for_matching(item["content"]).strip()
            match_idx = find_indexed_text_match(
                paragraph_index,
                item_content_clean,
                item_content_normalized,
                paragraph_cursor,
            )
            if match_idx is None:
                continue
            matched_paragraph = paragraphs[match_idx]["para"]
            paragraph_cursor = match_idx + 1

            block_corrections.sort(
                key=lambda corr: (
                    corr.get("preferred_start")
                    if isinstance(corr.get("preferred_start"), int)
                    else item["content"].find(corr["original"])
                )
            )
            last_search_start = 0
            for corr in block_corrections:
                original = corr["original"]
                expected_start = -1
                preferred_start = corr.get("preferred_start")
                if isinstance(preferred_start, int) and preferred_start >= last_search_start:
                    end = preferred_start + len(original)
                    if item["content"][preferred_start:end] == original:
                        expected_start = preferred_start

                if expected_start == -1:
                    expected_start = item["content"].find(original, last_search_start)
                if expected_start == -1:
                    expected_start = item["content"].find(original)
                if expected_start != -1:
                    last_search_start = max(last_search_start, expected_start + len(original))

                explanation = (corr.get("explanation") or "").strip()
                _apply_correction_to_paragraph(
                    word_doc=doc,
                    paragraph=matched_paragraph,
                    original=original,
                    corrected=corr.get("corrected", original),
                    explanation=explanation,
                    add_comments=config.get("add_comments", True),
                    notify_terminal_punctuation=config.get("notify_terminal_punctuation", True),
                    preferred_start_clean=expected_start,
                )

        doc.SaveAs(output_path, FileFormat=12)
        try:
            doc.Close(False)
        except Exception:
            pass
        doc = None

        _normalize_track_changes_authors(output_path, commenter_name, commenter_initials)
        scrub_docx_metadata(output_path, commenter_name)
        print(f"\nSuccessfully saved tracked DOCX to: {output_path}")
    finally:
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:
                pass
        try:
            word.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


def process_docx_tracked(input_path, output_path, config, client):
    """Process DOCX with Word Track Changes and comments, including table content."""
    correction_plan, stats = build_correction_plan(input_path, config, client)
    process_docx_tracked_with_plan(input_path, output_path, correction_plan, config)
    return stats
