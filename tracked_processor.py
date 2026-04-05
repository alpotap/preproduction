import difflib
import win32com.client as win32

from document_processor import build_correction_plan


WD_FIND_STOP = 0
MAX_FIND_TEXT_LENGTH = 240


def _clean_paragraph_text(text):
    """Normalize Word paragraph text for LLM processing and matching."""
    if not text:
        return ""
    return text.replace("\r", "").replace("\x07", "").strip()


def _trim_paragraph_end_markers(text):
    """Remove trailing Word paragraph/cell markers for index-based matching."""
    if not text:
        return ""
    while text.endswith("\r") or text.endswith("\x07"):
        text = text[:-1]
    return text


def _collect_all_paragraphs_from_docx(doc):
    """Collect paragraphs from the document body and table cells for Word COM objects."""
    all_paragraphs = list(doc.Paragraphs)
    for table in doc.Tables:
        for row in table.Rows:
            for cell in row.Cells:
                all_paragraphs.extend(cell.Range.Paragraphs)
    return all_paragraphs


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


def _apply_correction_to_paragraph(word_doc, paragraph, original, corrected, explanation, add_comments):
    """Apply one correction to a Word paragraph with Track Changes enabled."""
    if not original:
        return False

    para_range = paragraph.Range.Duplicate
    if para_range.End > para_range.Start:
        para_range.End = para_range.End - 1

    target = None

    if len(original) <= MAX_FIND_TEXT_LENGTH:
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
        raw_para_text = _trim_paragraph_end_markers(paragraph.Range.Text)
        start_idx = raw_para_text.find(original)
        if start_idx == -1:
            return False
        base_start = paragraph.Range.Start
        target = word_doc.Range(Start=base_start + start_idx, End=base_start + start_idx + len(original))

    if add_comments and explanation:
        try:
            word_doc.Comments.Add(Range=target, Text=explanation)
        except Exception:
            pass

    _apply_diff_to_range(word_doc, target, original, corrected)
    return True


def process_docx_tracked_with_plan(input_path, output_path, correction_plan, config):
    """Apply a precomputed correction plan to a DOCX using Track Changes and comments."""
    print(f"Loading document with Track Changes mode: {input_path}")

    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    doc = None

    try:
        doc = word.Documents.Open(input_path)
        doc.TrackRevisions = True

        word_paragraphs = _collect_all_paragraphs_from_docx(doc)
        paragraphs = []
        for para in word_paragraphs:
            text = _clean_paragraph_text(para.Range.Text)
            if text:
                paragraphs.append({"para": para, "content": text})

        print("Applying tracked changes...")

        paragraph_cursor = 0
        for item in correction_plan:
            block_corrections = item.get("corrections", [])
            if not block_corrections:
                continue

            matched_paragraph = None
            for idx in range(paragraph_cursor, len(paragraphs)):
                if paragraphs[idx]["content"] == item["content"]:
                    matched_paragraph = paragraphs[idx]["para"]
                    paragraph_cursor = idx + 1
                    break

            if matched_paragraph is None:
                continue

            block_corrections.sort(key=lambda x: item["content"].find(x["original"]))
            for corr in block_corrections:
                explanation = (corr.get("explanation") or "").strip()
                _apply_correction_to_paragraph(
                    word_doc=doc,
                    paragraph=matched_paragraph,
                    original=corr["original"],
                    corrected=corr.get("corrected", corr["original"]),
                    explanation=explanation,
                    add_comments=config.get("add_comments", True),
                )

        doc.SaveAs(output_path, FileFormat=12)
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


def process_docx_tracked(input_path, output_path, config, client):
    """Process DOCX with Word Track Changes and comments, including table content."""
    correction_plan, stats = build_correction_plan(input_path, config, client)
    process_docx_tracked_with_plan(input_path, output_path, correction_plan, config)
    return stats
