import re
import uuid
import base64
from email import message_from_string
from docx import Document

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

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

def get_content_from_mhtml(mhtml_file, image_output_dir):
    """Extracts structured content (text and images) from an MHTML file."""
    if not BeautifulSoup:
        print("Missing dependencies for web processing. Please run: pip install beautifulsoup4")
        return []

    try:
        image_asset_dir = image_output_dir / mhtml_file.stem
        image_asset_dir.mkdir(exist_ok=True)

        with open(mhtml_file, 'r', encoding='utf-8') as f:
            mhtml_data = f.read()
        
        msg = message_from_string(mhtml_data)
        html_content = None
        cid_map = {}
        location_map = {}

        # First pass: extract and save all image parts, mapping them by Content-ID
        for part in msg.walk():
            if part.get_content_maintype() == 'image':
                try:
                    cid = part.get('Content-ID', '').strip('<>')
                    location = part.get('Content-Location')
                    image_data = part.get_payload(decode=True)
                    ext = part.get_content_subtype() or 'png'
                    if 'svg' in ext:
                        ext = 'svg'
                    image_filename = f"{uuid.uuid4()}.{ext}"
                    image_path = image_asset_dir / image_filename
                    with open(image_path, 'wb') as img_file:
                        img_file.write(image_data)
                    if cid:
                        cid_map[cid] = image_path
                    if location:
                        location_map[location] = image_path
                except Exception as e:
                    print(f"  [!] Warning: Could not process an image part: {e}")

        # Second pass: find the HTML content
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                html_content = part.get_payload(decode=True).decode('utf-8')
                break
        
        if not html_content:
            print(f"No HTML content found in {mhtml_file}")
            return []

        soup = BeautifulSoup(html_content, 'html.parser')
        content_blocks = []
        
        tags_to_find = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'img']

        for element in soup.find_all(tags_to_find):
            if any(p.name in tags_to_find for p in element.find_parents()):
                continue

            if element.name == 'img':
                src = element.get('src', '')
                image_path = None
                if src.startswith('cid:'):
                    cid = src[4:]
                    image_path = cid_map.get(cid)
                elif src in location_map:
                    image_path = location_map.get(src)
                elif src.startswith('data:image'):
                    try:
                        header, encoded = src.split(',', 1)
                        ext = re.search(r'/(.*?);', header).group(1)
                        if 'svg' in ext: ext = 'svg'
                        image_data = base64.b64decode(encoded)
                        image_filename = f"{uuid.uuid4()}.{ext}"
                        image_path = image_asset_dir / image_filename
                        with open(image_path, 'wb') as img_file:
                            img_file.write(image_data)
                    except Exception:
                        pass
                if image_path:
                    content_blocks.append({'type': 'image', 'path': image_path})
            else: # h*, p, li
                text = element.get_text().strip()
                if text:
                    style = 'Normal'
                    if element.name.startswith('h'):
                        try:
                            level = int(element.name[1])
                            if 1 <= level <= 6:
                                style = f"Heading {level}"
                        except (ValueError, IndexError):
                            pass
                    elif element.name == 'li':
                        parent_list = element.find_parent(['ul', 'ol'])
                        if parent_list:
                            style = 'List Bullet' if parent_list.name == 'ul' else 'List Number'
                    content_blocks.append({'type': 'text', 'content': text, 'style': style})
        
        print(f"Extracted {len(content_blocks)} content blocks (text and images) from {mhtml_file.name}")
        return content_blocks
    except Exception as e:
        print(f"Error processing MHTML file {mhtml_file}: {e}")
        return []