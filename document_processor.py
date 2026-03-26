import difflib
import copy
from lxml import etree
from docx import Document
from docx.shared import RGBColor, Inches
from docx.oxml.ns import qn
from llm_service import get_corrections_from_llm


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
            # Insert an empty paragraph after the image paragraph.
            para._p.addnext(copy.deepcopy(para._p))
            new_next = para._p.getnext()
            for child in list(new_next):
                new_next.remove(child)
            inserted_count += 1

    return inserted_count

def _rewrite_paragraph_preserving_images(para, block_content, block_corrections, config):
    """
    Rewrites the text of a paragraph that contains both text and image runs.
    Drawing/picture nodes are preserved; only text-bearing runs are modified.
    """
    p = para._p

    # Collect drawing elements that must be preserved, keyed by their position
    # We'll detach them, rebuild text runs, then reattach drawings in order.
    drawing_nodes = []
    for r_elem in list(p.findall(qn('w:r'))):
        for child_tag in (qn('w:drawing'), qn('w:pict')):
            d = r_elem.find(child_tag)
            if d is not None:
                # Record position index among all children of <w:p>
                idx = list(p).index(r_elem)
                drawing_nodes.append((idx, copy.deepcopy(r_elem)))

    # Remove all existing <w:r> children (we'll rebuild text ones below)
    for r_elem in list(p.findall(qn('w:r'))):
        p.remove(r_elem)

    # --- Build new text runs (same logic as the normal path) ---
    def _add_run_elem(text, bold=False, color=None, italic=False):
        r = etree.SubElement(p, qn('w:r'))
        t = etree.SubElement(r, qn('w:t'))
        t.text = text
        if text.startswith(' ') or text.endswith(' '):
            t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        if bold or color or italic:
            rpr = etree.Element(qn('w:rPr'))
            r.insert(0, rpr)
            if bold:
                etree.SubElement(rpr, qn('w:b'))
            if color:
                clr = etree.SubElement(rpr, qn('w:color'))
                clr.set(qn('w:val'), color)
            if italic:
                etree.SubElement(rpr, qn('w:i'))
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

        corrected_text = corr.get('corrected', orig)
        matcher = difflib.SequenceMatcher(None, orig, corrected_text)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                _add_run_elem(corrected_text[j1:j2])
            elif tag in ('replace', 'insert'):
                if config.get('highlight_corrections', True):
                    _add_run_elem(corrected_text[j1:j2], bold=True, color='FF0000')
                else:
                    _add_run_elem(corrected_text[j1:j2])

        if config.get('add_comments', True):
            explanation = corr.get('explanation', '').strip()
            if explanation:
                _add_run_elem(f" [{explanation}]", italic=True, color='0000FF')

        last_end = end

    if block_content[last_end:]:
        _add_run_elem(block_content[last_end:])

    # Re-insert drawing runs at their original positions
    # Since we cleared all runs, just append them at the end to preserve their content
    for _idx, r_elem in drawing_nodes:
        p.append(r_elem)


def apply_corrections_to_batch(batch_items, config, client, stats):
    """Processes a batch of paragraphs in-place."""
    # batch_items is a list of dicts: {'para': paragraph_object, 'content': text_string}
    # Join text for the prompt
    full_text = "\n".join([b['content'] for b in batch_items])
    
    corrections, tokens, llm_time = get_corrections_from_llm(full_text, config, client)
    stats["total_tokens_generated"] += tokens
    stats["total_llm_time"] += llm_time

    for item in batch_items:
        para = item['para']
        block_content = item['content']
        stats["total_text_size"] += len(item['content'])
        
        # Filter corrections relevant to this specific paragraph
        block_corrections = []
        for corr in corrections:
            if corr.get('original') and corr['original'] in block_content:
                if corr.get('original') != corr.get('corrected'):
                    block_corrections.append(corr)
        
        if not block_corrections:
            continue
        
        if _paragraph_contains_image(para):
            # Safe path: rewrite text runs while preserving drawing/picture nodes
            _rewrite_paragraph_preserving_images(para, block_content, block_corrections, config)
            continue

        # Clear the paragraph content to rewrite it with highlights
        # This preserves the paragraph style and position in the doc
        para.clear()
        
        block_corrections.sort(key=lambda x: block_content.find(x['original']))
        
        last_end = 0
        for corr in block_corrections:
            orig = corr['original']
            start = block_content.find(orig, last_end)
            if start == -1: continue
            
            end = start + len(orig)
            para.add_run(block_content[last_end:start])
            
            corrected_text = corr.get('corrected', orig)
            matcher = difflib.SequenceMatcher(None, orig, corrected_text)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == 'equal':
                    para.add_run(corrected_text[j1:j2])
                elif tag == 'replace' or tag == 'insert':
                    run = para.add_run(corrected_text[j1:j2])
                    if config.get('highlight_corrections', True):
                        run.bold = True
                        run.font.color.rgb = RGBColor(255, 0, 0)

            if config.get('add_comments', True):
                explanation = corr.get('explanation', '').strip()
                if explanation:
                    exp_run = para.add_run(f" [{explanation}]")
                    exp_run.italic = True
                    exp_run.font.color.rgb = RGBColor(0, 0, 255)
            
            last_end = end
        para.add_run(block_content[last_end:])

def process_docx(input_path, output_path, config, client):
    """Loads a DOCX, corrects text in-place (preserving images), and saves to output_path."""
    print(f"Loading document: {input_path}")
    doc = Document(input_path)

    inserted = _insert_blank_line_before_images(doc)
    if inserted:
        print(f"Inserted {inserted} blank line(s) before image paragraph(s).")
    
    stats = {
        "total_text_size": 0,
        "total_llm_time": 0,
        "total_tokens_generated": 0
    }
    print("Processing document paragraphs...")

    current_batch = []
    current_word_count = 0
    
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
            
        # Add to batch
        if current_word_count + len(text.split()) > 500 and current_batch:
            apply_corrections_to_batch(current_batch, config, client, stats)
            current_batch = []
            current_word_count = 0
        
        current_batch.append({'para': para, 'content': para.text})
        current_word_count += len(text.split())

    if current_batch:
        apply_corrections_to_batch(current_batch, config, client, stats)

    doc.save(output_path)
    print(f"\nSuccessfully saved corrected DOCX to: {output_path}")
    return stats