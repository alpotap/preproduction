import re
from docx import Document

def get_content_from_docx(file_path):
    """Extracts a list of text blocks from a .docx file's paragraphs, attempting to filter boilerplate."""
    try:
        doc = Document(file_path)
        
        all_paragraphs = []
        for p in doc.paragraphs:
            if p.text.strip():
                all_paragraphs.append(p)

        content_started = False
        content_paragraph_objects = []

        for p in all_paragraphs:
            if not content_started:
                # Heuristic to find the start of the actual content.
                if re.match(r'^\d+-\d+.*', p.text.strip()):
                    content_started = True
            
            if content_started:
                content_paragraph_objects.append(p)

        if not content_paragraph_objects:
            # Fallback to using all paragraphs if marker not found
            print("  [!] Warning: Document start marker not found. Processing all paragraphs.")
            content_paragraph_objects = all_paragraphs

        return [{'type': 'text', 'content': p.text, 'style': p.style.name} for p in content_paragraph_objects]
    except Exception as e:
        print(f"Error reading docx file {file_path}: {e}")
        return None