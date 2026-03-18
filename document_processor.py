import difflib
from docx import Document
from docx.shared import RGBColor, Inches
from llm_service import get_corrections_from_llm

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