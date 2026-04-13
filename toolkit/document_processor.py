"""Builds shared correction plans and renders inline and hybrid DOCX outputs."""

import difflib
import copy
from lxml import etree
from docx import Document
from docx.shared import RGBColor
from docx.oxml.ns import qn
from toolkit.llm_service import get_corrections_from_llm
try:
    from toolkit.prompts import get_prompt_max_input_words, DEFAULT_PROMPT_KEY
except (ImportError, ModuleNotFoundError):
    DEFAULT_PROMPT_KEY = "default"

    def get_prompt_max_input_words(prompt_key, fallback=500):
        return fallback


def _paragraph_contains_image(paragraph):
    """Returns True if the paragraph contains an inline/floating image."""
    p = paragraph._p
    return (
        p.find(f".//{qn('w:drawing')}") is not None
        or p.find(f".//{qn('w:pict')}") is not None
    )


def _insert_blank_line_before_images(doc):
    """Ensures a blank paragraph exists before and after every image paragraph."""
    inserted_count = 0
    for para in list(doc.paragraphs):
        if not _paragraph_contains_image(para):
            continue

        prev = para._p.getprevious()
        prev_is_blank_para = (
            prev is not None
            and prev.tag.endswith("}p")
            and "".join(prev.itertext()).strip() == ""
        )

        if not prev_is_blank_para:
            para.insert_paragraph_before("")
            inserted_count += 1

        nxt = para._p.getnext()
        next_is_blank_para = (
            nxt is not None
            and nxt.tag.endswith("}p")
            and "".join(nxt.itertext()).strip() == ""
        )

        if not next_is_blank_para:
            para._p.addnext(copy.deepcopy(para._p))
            new_next = para._p.getnext()
            for child in list(new_next):
                new_next.remove(child)
            inserted_count += 1

    return inserted_count


def _preserve_soft_breaks(original_text, corrected_text):
    """Reinsert original soft line breaks (Shift+Enter) if the correction dropped them."""
    break_char = "\n"
    original_breaks = original_text.count(break_char)
    if original_breaks == 0:
        return corrected_text
    if corrected_text.count(break_char) >= original_breaks:
        return corrected_text

    parts = original_text.split(break_char)
    if len(parts) <= 1:
        return corrected_text

    total_original_len = sum(len(p) for p in parts)
    if total_original_len <= 0:
        return corrected_text

    corrected_len = len(corrected_text)
    target_lengths = [round((len(p) / total_original_len) * corrected_len) for p in parts]
    diff = corrected_len - sum(target_lengths)
    if target_lengths:
        target_lengths[-1] += diff

    chunks = []
    cursor = 0
    for i, target in enumerate(target_lengths):
        remaining = corrected_len - cursor
        if i == len(target_lengths) - 1:
            chunk_len = remaining
        else:
            chunk_len = max(0, min(int(target), remaining))
        chunks.append(corrected_text[cursor:cursor + chunk_len])
        cursor += chunk_len

    return break_char.join(chunks)


def _build_deletion_marker(deleted_text, show_marker=True):
    """Builds a visible marker for deleted text so removals are obvious in output."""
    if not deleted_text or not show_marker:
        return ""
    visible = deleted_text.replace("\n", r"\n")
    return f"[-{visible}-]"


def _collect_all_paragraphs(doc):
    """Collect paragraphs from the document body and table cells."""
    all_paragraphs = list(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                all_paragraphs.extend(cell.paragraphs)
    return all_paragraphs


def _filter_corrections_for_block(block_content, corrections):
    """Return only corrections that apply to one paragraph/block of text."""
    block_corrections = []
    for corr in corrections:
        original = corr.get('original')
        corrected = corr.get('corrected', original)
        if original and original in block_content and original != corrected:
            block_corrections.append(corr)
    return block_corrections


def _rewrite_paragraph_preserving_images(para, block_content, block_corrections, config):
    """
    Rewrites the text of a paragraph that contains both text and image runs.
    Drawing/picture nodes are preserved; only text-bearing runs are modified.
    """
    p = para._p

    drawing_nodes = []
    for r_elem in list(p.findall(qn('w:r'))):
        for child_tag in (qn('w:drawing'), qn('w:pict')):
            d = r_elem.find(child_tag)
            if d is not None:
                idx = list(p).index(r_elem)
                drawing_nodes.append((idx, copy.deepcopy(r_elem)))

    for r_elem in list(p.findall(qn('w:r'))):
        p.remove(r_elem)

    def _add_run_elem(text, bold=False, color=None, italic=False, strike=False):
        r = etree.SubElement(p, qn('w:r'))
        t = etree.SubElement(r, qn('w:t'))
        t.text = text
        if text.startswith(' ') or text.endswith(' '):
            t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        if bold or color or italic or strike:
            rpr = etree.Element(qn('w:rPr'))
            r.insert(0, rpr)
            if bold:
                etree.SubElement(rpr, qn('w:b'))
            if color:
                clr = etree.SubElement(rpr, qn('w:color'))
                clr.set(qn('w:val'), color)
            if italic:
                etree.SubElement(rpr, qn('w:i'))
            if strike:
                etree.SubElement(rpr, qn('w:strike'))
        return r

    block_corrections.sort(key=lambda x: block_content.find(x['original']))
    last_end = 0
    for corr in block_corrections:
        orig = corr['original']
        start = block_content.find(orig, last_end)
        if start == -1:
            continue
        end = start + len(orig)

        if block_content[last_end:start]:
            _add_run_elem(block_content[last_end:start])

        corrected_text = _preserve_soft_breaks(orig, corr.get('corrected', orig))
        matcher = difflib.SequenceMatcher(None, orig, corrected_text)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                _add_run_elem(corrected_text[j1:j2])
            elif tag in ('replace', 'insert'):
                if config.get('highlight_corrections', True):
                    _add_run_elem(corrected_text[j1:j2], bold=True, color='FF0000')
                else:
                    _add_run_elem(corrected_text[j1:j2])
            elif tag == 'delete':
                deleted_marker = _build_deletion_marker(
                    orig[i1:i2],
                    show_marker=config.get('show_deletion_markers', True),
                )
                if deleted_marker:
                    _add_run_elem(deleted_marker, color='FF0000', strike=True)

        if config.get('add_comments', True):
            explanation = corr.get('explanation', '').strip()
            if explanation:
                _add_run_elem(f" [{explanation}]", italic=True, color='0000FF')

        last_end = end

    if block_content[last_end:]:
        _add_run_elem(block_content[last_end:])

    for _idx, r_elem in drawing_nodes:
        p.append(r_elem)


def _append_batch_to_correction_plan(current_batch, config, client, correction_plan, stats):
    """Gets LLM corrections for one batch and appends normalized entries to correction_plan."""
    full_text = "\n".join([b['content'] for b in current_batch])
    corrections, input_tokens, output_tokens, llm_time = get_corrections_from_llm(full_text, config, client)
    stats["total_input_tokens"] += input_tokens
    stats["total_tokens_generated"] += output_tokens
    stats["total_llm_time"] += llm_time

    for item in current_batch:
        block_content = item['content']
        stats["total_text_size"] += len(block_content)
        correction_plan.append({
            'content': block_content,
            'corrections': _filter_corrections_for_block(block_content, corrections)
        })


def _apply_inline_corrections_to_paragraph(para, block_content, block_corrections, config):
    """Apply precomputed corrections to one paragraph in inline mode."""
    if not block_corrections:
        return

    if _paragraph_contains_image(para):
        _rewrite_paragraph_preserving_images(para, block_content, block_corrections, config)
        return

    para.clear()
    block_corrections.sort(key=lambda x: block_content.find(x['original']))

    last_end = 0
    for corr in block_corrections:
        orig = corr['original']
        start = block_content.find(orig, last_end)
        if start == -1:
            continue

        end = start + len(orig)
        para.add_run(block_content[last_end:start])

        corrected_text = _preserve_soft_breaks(orig, corr.get('corrected', orig))
        matcher = difflib.SequenceMatcher(None, orig, corrected_text)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                para.add_run(corrected_text[j1:j2])
            elif tag == 'replace' or tag == 'insert':
                run = para.add_run(corrected_text[j1:j2])
                if config.get('highlight_corrections', True):
                    run.bold = True
                    run.font.color.rgb = RGBColor(255, 0, 0)
            elif tag == 'delete':
                deleted_marker = _build_deletion_marker(
                    orig[i1:i2],
                    show_marker=config.get('show_deletion_markers', True),
                )
                if deleted_marker:
                    deleted_run = para.add_run(deleted_marker)
                    deleted_run.font.strike = True
                    deleted_run.font.color.rgb = RGBColor(255, 0, 0)

        if config.get('add_comments', True):
            explanation = corr.get('explanation', '').strip()
            if explanation:
                exp_run = para.add_run(f" [{explanation}]")
                exp_run.italic = True
                exp_run.font.color.rgb = RGBColor(0, 0, 255)

        last_end = end

    para.add_run(block_content[last_end:])


def build_correction_plan(input_path, config, client, should_cancel=None):
    """Build one correction plan from LLM output that can drive multiple renderers."""
    def _raise_if_canceled():
        if callable(should_cancel) and should_cancel():
            raise RuntimeError("Canceled by user request")

    _raise_if_canceled()
    print(f"Loading document: {input_path}")
    doc = Document(input_path)
    prompt_key = config.get('active_prompt', DEFAULT_PROMPT_KEY)
    max_input_words = get_prompt_max_input_words(prompt_key, fallback=500)
    print(f"Using prompt context size: {max_input_words} words")

    stats = {
        "total_text_size": 0,
        "total_llm_time": 0,
        "total_input_tokens": 0,
        "total_tokens_generated": 0,
    }

    correction_plan = []
    all_paragraphs = _collect_all_paragraphs(doc)

    current_batch = []
    current_word_count = 0

    for para in all_paragraphs:
        _raise_if_canceled()
        text = para.text.strip()
        if not text:
            continue

        if current_word_count + len(text.split()) > max_input_words and current_batch:
            _raise_if_canceled()
            _append_batch_to_correction_plan(current_batch, config, client, correction_plan, stats)

            current_batch = []
            current_word_count = 0

        current_batch.append({'content': para.text})
        current_word_count += len(text.split())

    if current_batch:
        _raise_if_canceled()
        _append_batch_to_correction_plan(current_batch, config, client, correction_plan, stats)

    return correction_plan, stats


def apply_inline_correction_plan(input_path, output_path, correction_plan, config):
    """Apply a precomputed correction plan to a DOCX in inline format."""
    print(f"Loading document: {input_path}")
    doc = Document(input_path)

    inserted = _insert_blank_line_before_images(doc)
    if inserted:
        print(f"Inserted {inserted} blank line(s) before image paragraph(s).")

    print("Applying inline corrections from shared correction plan...")

    all_paragraphs = _collect_all_paragraphs(doc)
    paragraphs = [
        {'para': para, 'content': para.text}
        for para in all_paragraphs
        if para.text and para.text.strip()
    ]

    paragraph_cursor = 0
    for item in correction_plan:
        block_corrections = item.get('corrections', [])
        if not block_corrections:
            continue

        matched_paragraph = None
        for idx in range(paragraph_cursor, len(paragraphs)):
            if paragraphs[idx]['content'] == item['content']:
                matched_paragraph = paragraphs[idx]['para']
                paragraph_cursor = idx + 1
                break

        if matched_paragraph is None:
            continue

        _apply_inline_corrections_to_paragraph(
            matched_paragraph,
            item['content'],
            block_corrections,
            config,
        )

    doc.save(output_path)
    print(f"\nSuccessfully saved corrected DOCX to: {output_path}")


def process_docx(input_path, output_path, config, client):
    """Loads a DOCX, corrects text in-place (preserving images), and saves to output_path."""
    correction_plan, stats = build_correction_plan(input_path, config, client)
    apply_inline_correction_plan(input_path, output_path, correction_plan, config)
    return stats


# ---------------------------------------------------------------------------
# Hybrid output: inline red text changes + Word XML comment explanations
# ---------------------------------------------------------------------------

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_COMMENTS_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
)
_COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)


def _apply_hybrid_corrections_to_paragraph(para, block_content, block_corrections, config, comment_collector):
    """Inline red text changes with explanations stored as Word XML comments instead of inline text."""
    if not block_corrections:
        return

    if _paragraph_contains_image(para):
        # Apply inline changes to image paragraphs but suppress inline explanation text.
        hybrid_config = dict(config)
        hybrid_config['add_comments'] = False
        _rewrite_paragraph_preserving_images(para, block_content, block_corrections, hybrid_config)
        # Gather all explanations and attach them as a single comment spanning the
        # paragraph, since individual run anchoring is not feasible after the rewrite.
        explanations = [
            corr.get('explanation', '').strip()
            for corr in block_corrections
            if corr.get('explanation', '').strip()
        ]
        if explanations:
            p = para._p
            comment_id = len(comment_collector)
            comment_start = etree.Element(qn('w:commentRangeStart'))
            comment_start.set(qn('w:id'), str(comment_id))
            p.insert(0, comment_start)
            comment_end = etree.Element(qn('w:commentRangeEnd'))
            comment_end.set(qn('w:id'), str(comment_id))
            p.append(comment_end)
            ref_run = etree.SubElement(p, qn('w:r'))
            ref_rpr = etree.SubElement(ref_run, qn('w:rPr'))
            ref_style = etree.SubElement(ref_rpr, qn('w:rStyle'))
            ref_style.set(qn('w:val'), 'CommentReference')
            comment_ref = etree.SubElement(ref_run, qn('w:commentReference'))
            comment_ref.set(qn('w:id'), str(comment_id))
            comment_collector.append((comment_id, ' | '.join(explanations)))
        return

    para.clear()
    p = para._p
    block_corrections.sort(key=lambda x: block_content.find(x['original']))

    last_end = 0
    for corr in block_corrections:
        orig = corr['original']
        start = block_content.find(orig, last_end)
        if start == -1:
            continue
        end = start + len(orig)

        prefix = block_content[last_end:start]
        if prefix:
            para.add_run(prefix)

        explanation = corr.get('explanation', '').strip()
        comment_id = None
        if explanation:
            comment_id = len(comment_collector)
            comment_start = etree.Element(qn('w:commentRangeStart'))
            comment_start.set(qn('w:id'), str(comment_id))
            p.append(comment_start)

        corrected_text = _preserve_soft_breaks(orig, corr.get('corrected', orig))
        matcher = difflib.SequenceMatcher(None, orig, corrected_text)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                para.add_run(corrected_text[j1:j2])
            elif tag in ('replace', 'insert'):
                run = para.add_run(corrected_text[j1:j2])
                if config.get('highlight_corrections', True):
                    run.bold = True
                    run.font.color.rgb = RGBColor(255, 0, 0)
            elif tag == 'delete':
                deleted_marker = _build_deletion_marker(
                    orig[i1:i2],
                    show_marker=config.get('show_deletion_markers', True),
                )
                if deleted_marker:
                    deleted_run = para.add_run(deleted_marker)
                    deleted_run.font.strike = True
                    deleted_run.font.color.rgb = RGBColor(255, 0, 0)

        if explanation:
            comment_end = etree.Element(qn('w:commentRangeEnd'))
            comment_end.set(qn('w:id'), str(comment_id))
            p.append(comment_end)

            ref_run = etree.SubElement(p, qn('w:r'))
            ref_run_pr = etree.SubElement(ref_run, qn('w:rPr'))
            ref_style = etree.SubElement(ref_run_pr, qn('w:rStyle'))
            ref_style.set(qn('w:val'), 'CommentReference')
            comment_ref = etree.SubElement(ref_run, qn('w:commentReference'))
            comment_ref.set(qn('w:id'), str(comment_id))

            comment_collector.append((comment_id, explanation))

        last_end = end

    suffix = block_content[last_end:]
    if suffix:
        para.add_run(suffix)


def _build_comments_xml(comment_items):
    """Return bytes for word/comments.xml from a list of (comment_id, text) pairs."""
    root = etree.Element(f'{{{_W_NS}}}comments', nsmap={'w': _W_NS})
    for comment_id, comment_text in comment_items:
        comment = etree.SubElement(root, f'{{{_W_NS}}}comment')
        comment.set(f'{{{_W_NS}}}id', str(comment_id))
        comment.set(f'{{{_W_NS}}}author', 'AI Reviewer')
        comment.set(f'{{{_W_NS}}}date', '2026-01-01T00:00:00Z')
        comment.set(f'{{{_W_NS}}}initials', 'AI')

        paragraph = etree.SubElement(comment, f'{{{_W_NS}}}p')
        run = etree.SubElement(paragraph, f'{{{_W_NS}}}r')
        text = etree.SubElement(run, f'{{{_W_NS}}}t')
        text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        text.text = comment_text

    return etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)


def _inject_comments_into_docx(docx_path, comment_items):
    """Post-process a saved docx zip to add word/comments.xml and required relationships."""
    import re as _re
    import zipfile as _zipfile

    comments_xml = _build_comments_xml(comment_items)

    with _zipfile.ZipFile(docx_path, 'r') as source_zip:
        file_map = {name: source_zip.read(name) for name in source_zip.namelist()}

    rels_key = 'word/_rels/document.xml.rels'
    if rels_key in file_map:
        rels_text = file_map[rels_key].decode('utf-8')
        if _COMMENTS_REL_TYPE not in rels_text:
            existing_ids = set(_re.findall(r'Id="([^"]+)"', rels_text))
            rel_id = 'rIdComments'
            counter = 0
            while rel_id in existing_ids:
                counter += 1
                rel_id = f'rIdComments{counter}'

            relation = (
                f'<Relationship Id="{rel_id}" '
                f'Type="{_COMMENTS_REL_TYPE}" '
                'Target="comments.xml"/>'
            )
            rels_text = rels_text.replace('</Relationships>', f'{relation}</Relationships>')
            file_map[rels_key] = rels_text.encode('utf-8')

    content_types_key = '[Content_Types].xml'
    if content_types_key in file_map:
        content_types = file_map[content_types_key].decode('utf-8')
        if 'comments.xml' not in content_types:
            override = (
                '<Override PartName="/word/comments.xml" '
                f'ContentType="{_COMMENTS_CONTENT_TYPE}"/>'
            )
            content_types = content_types.replace('</Types>', f'{override}</Types>')
            file_map[content_types_key] = content_types.encode('utf-8')

    file_map['word/comments.xml'] = comments_xml

    with _zipfile.ZipFile(docx_path, 'w', _zipfile.ZIP_DEFLATED) as target_zip:
        for name, content in file_map.items():
            target_zip.writestr(name, content)


def apply_hybrid_correction_plan(input_path, output_path, correction_plan, config):
    """Apply a precomputed correction plan to a DOCX in hybrid format."""
    print(f"Loading document: {input_path}")
    doc = Document(input_path)

    inserted = _insert_blank_line_before_images(doc)
    if inserted:
        print(f"Inserted {inserted} blank line(s) before image paragraph(s).")

    print("Applying hybrid corrections from shared correction plan...")

    all_paragraphs = _collect_all_paragraphs(doc)
    paragraphs = [
        {'para': para, 'content': para.text}
        for para in all_paragraphs
        if para.text and para.text.strip()
    ]

    comment_collector = []
    paragraph_cursor = 0

    for item in correction_plan:
        block_corrections = item.get('corrections', [])
        if not block_corrections:
            continue

        matched_paragraph = None
        for idx in range(paragraph_cursor, len(paragraphs)):
            if paragraphs[idx]['content'] == item['content']:
                matched_paragraph = paragraphs[idx]['para']
                paragraph_cursor = idx + 1
                break

        if matched_paragraph is None:
            continue

        _apply_hybrid_corrections_to_paragraph(
            matched_paragraph,
            item['content'],
            block_corrections,
            config,
            comment_collector,
        )

    doc.save(output_path)

    if comment_collector:
        _inject_comments_into_docx(output_path, comment_collector)

    print(f"\nSuccessfully saved hybrid DOCX to: {output_path}")
