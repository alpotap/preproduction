import difflib
from docx import Document
from docx.shared import RGBColor, Inches
from llm_service import get_corrections_from_llm

try:
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    from io import BytesIO
except ImportError:
    svg2rlg = renderPM = BytesIO = None

def process_batch(doc, batch_blocks, config, client, stats):
    """Processes a batch of text blocks, sends them to LLM, and adds them to the DOCX."""
    # Join text for the prompt
    full_text = "\n".join([b['content'] for b in batch_blocks])
    
    corrections, tokens, llm_time = get_corrections_from_llm(full_text, config, client)
    stats["total_tokens_generated"] += tokens
    stats["total_llm_time"] += llm_time

    for block in batch_blocks:
        stats["total_text_size"] += len(block['content'])
        
        new_para = doc.add_paragraph()
        if block.get('style'):
            try:
                new_para.style = block.get('style')
            except KeyError:
                pass
        
        original_text = block['content']
        block_corrections = []
        for corr in corrections:
            if corr.get('original') and corr['original'] in original_text:
                if corr.get('original') != corr.get('corrected'):
                    block_corrections.append(corr)
        
        if not block_corrections:
            new_para.add_run(original_text)
            continue
            
        block_corrections.sort(key=lambda x: original_text.find(x['original']))
        
        last_end = 0
        for corr in block_corrections:
            orig = corr['original']
            start = original_text.find(orig, last_end)
            if start == -1: continue
            
            end = start + len(orig)
            new_para.add_run(original_text[last_end:start])
            
            corrected_text = corr.get('corrected', orig)
            matcher = difflib.SequenceMatcher(None, orig, corrected_text)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == 'equal':
                    new_para.add_run(corrected_text[j1:j2])
                elif tag == 'replace' or tag == 'insert':
                    run = new_para.add_run(corrected_text[j1:j2])
                    if config.get('highlight_corrections', True):
                        run.bold = True
                        run.font.color.rgb = RGBColor(255, 0, 0)

            if config.get('add_comments', True):
                explanation = corr.get('explanation', '').strip()
                if explanation:
                    exp_run = new_para.add_run(f" [{explanation}]")
                    exp_run.italic = True
                    exp_run.font.color.rgb = RGBColor(0, 0, 255)
            
            last_end = end
        new_para.add_run(original_text[last_end:])

def create_docx_output(content_blocks, config, client, output_path):
    """Processes paragraphs and saves the corrected output as a .docx file."""
    new_doc = Document()
    stats = {
        "total_text_size": 0,
        "total_llm_time": 0,
        "total_tokens_generated": 0
    }
    print("Processing content blocks for DOCX output...")

    current_batch = []
    current_word_count = 0
    
    for i, block in enumerate(content_blocks):
        if block['type'] == 'image':
            if current_batch:
                process_batch(new_doc, current_batch, config, client, stats)
                current_batch = []
                current_word_count = 0
                
            try:
                if str(block['path']).lower().endswith('.svg') and svg2rlg:
                    drawing = svg2rlg(str(block['path']))
                    png_io = BytesIO()
                    renderPM.drawToFile(drawing, png_io, fmt="PNG")
                    png_io.seek(0)
                    new_doc.add_picture(png_io, width=Inches(6.0))
                else:
                    new_doc.add_picture(str(block['path']), width=Inches(6.0))
            except Exception as e:
                print(f"  [!] Could not add image: {e}")
            continue
        
        if not block.get('content', '').strip(): continue
        if current_word_count + len(block['content'].split()) > 500 and current_batch:
            process_batch(new_doc, current_batch, config, client, stats)
            current_batch = []
            current_word_count = 0
        current_batch.append(block)
        current_word_count += len(block['content'].split())

    if current_batch:
        process_batch(new_doc, current_batch, config, client, stats)

    new_doc.save(output_path)
    print(f"\nSuccessfully saved corrected DOCX to: {output_path}")
    return stats