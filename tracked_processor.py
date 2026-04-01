import difflib
import time
import win32com.client as win32
from llm_service import get_corrections_from_llm


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


def _apply_diff_to_range(word_doc, target_range, original, corrected):
    """Apply minimal tracked edits to a Word range using a character diff."""
    base_start = target_range.Start
    matcher = difflib.SequenceMatcher(None, original, corrected)

    for tag, i1, i2, j1, j2 in reversed(matcher.get_opcodes()):
        if tag == 'equal':
            continue

        edit_start = base_start + i1
        edit_end = base_start + i2
        replacement_text = corrected[j1:j2]

        if tag == 'insert':
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
    # Exclude paragraph mark from search range.
    if para_range.End > para_range.Start:
        para_range.End = para_range.End - 1

    target = None

    # Fast path: Word Find API for shorter strings.
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

    # Fallback path: direct range by character offsets for long strings.
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


def _apply_corrections_batch_word(word_doc, batch_items, config, client, stats):
    """Get corrections from LLM and apply them as tracked changes/comments in Word."""
    full_text = "\n".join([b['content'] for b in batch_items])

    corrections, tokens, llm_time = get_corrections_from_llm(full_text, config, client)
    stats["total_tokens_generated"] += tokens
    stats["total_llm_time"] += llm_time

    for item in batch_items:
        para = item['para']
        block_content = item['content']
        stats["total_text_size"] += len(block_content)

        block_corrections = []
        for corr in corrections:
            if corr.get('original') and corr['original'] in block_content:
                if corr.get('original') != corr.get('corrected'):
                    block_corrections.append(corr)

        if not block_corrections:
            continue

        block_corrections.sort(key=lambda x: block_content.find(x['original']))
        for corr in block_corrections:
            explanation = (corr.get('explanation') or '').strip()
            _apply_correction_to_paragraph(
                word_doc=word_doc,
                paragraph=para,
                original=corr['original'],
                corrected=corr.get('corrected', corr['original']),
                explanation=explanation,
                add_comments=config.get('add_comments', True),
            )


def process_docx_tracked(input_path, output_path, config, client):
    """
    Process DOCX with Word Track Changes and Word comments.
    Corrections are proposed as revisions instead of inline text styling.
    """
    print(f"Loading document with Track Changes mode: {input_path}")

    stats = {
        "total_text_size": 0,
        "total_llm_time": 0,
        "total_tokens_generated": 0,
    }

    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    doc = None

    try:
        doc = word.Documents.Open(input_path)
        doc.TrackRevisions = True

        paragraphs = []
        for para in doc.Paragraphs:
            text = _clean_paragraph_text(para.Range.Text)
            if text:
                paragraphs.append({'para': para, 'content': text})

        print("Processing document paragraphs with tracked changes...")

        current_batch = []
        current_word_count = 0

        for item in paragraphs:
            text = item['content']
            word_count = len(text.split())

            if current_word_count + word_count > 500 and current_batch:
                _apply_corrections_batch_word(doc, current_batch, config, client, stats)
                current_batch = []
                current_word_count = 0

            current_batch.append(item)
            current_word_count += word_count

        if current_batch:
            _apply_corrections_batch_word(doc, current_batch, config, client, stats)

        doc.SaveAs(output_path, FileFormat=12)
        print(f"\nSuccessfully saved tracked DOCX to: {output_path}")
        return stats
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
