import os
import re
import json
import subprocess
import sys
from pathlib import Path
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.edge.service import Service
import time
from email import message_from_string
import argparse
from utils import load_config
from llm_service import get_corrections_from_llm

def install_package(package):
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    except subprocess.CalledProcessError:
        print(f"Failed to install {package}")

# Auto-install dependencies removed due to syntax issues
    pass

def extract_text_from_web(url):
    try:
        # Use Edge WebDriver for JS support
        service = Service()  # assumes msedgedriver.exe in PATH
        driver = webdriver.Edge(service=service)
        driver.get(url)
        time.sleep(15)  # wait for JS to load content
        # Capture MHTML snapshot
        mhtml_data = driver.execute_cdp_cmd("Page.captureSnapshot", {"format": "mhtml"})['data']
        driver.quit()
        # Save MHTML
        mhtml_path = Path(__file__).parent / "input" / "page.mhtml"
        mhtml_path.parent.mkdir(exist_ok=True)
        with open(mhtml_path, "w", encoding="utf-8") as f:
            f.write(mhtml_data)
        print(f"MHTML saved to {mhtml_path}")
        # Parse MHTML to extract HTML
        msg = message_from_string(mhtml_data)
        html_content = None
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                html_content = part.get_payload(decode=True).decode('utf-8')
                break
        if not html_content:
            return []
        soup = BeautifulSoup(html_content, 'html.parser')
        # Extract structured content
        structured_content = []
        for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li']):
            text = element.get_text().strip()
            if text:
                tag = element.name
                structured_content.append({'type': tag, 'text': text})
        print(f"Extracted {len(structured_content)} structured elements")
        return structured_content
    except Exception as e:
        print(f"Error fetching web content: {e}")
        return []

def save_mhtml(url, mhtml_path):
    try:
        service = Service()
        driver = webdriver.Edge(service=service)
        driver.get(url)
        time.sleep(25)
        mhtml_data = driver.execute_cdp_cmd("Page.captureSnapshot", {"format": "mhtml"})['data']
        driver.quit()
        mhtml_path.parent.mkdir(exist_ok=True)
        with open(mhtml_path, "w", encoding="utf-8") as f:
            f.write(mhtml_data)
        print(f"MHTML saved to {mhtml_path}")
    except Exception as e:
        print(f"Error saving MHTML for {url}: {e}")

def process_mhtml(mhtml_file, config, client):
    with open(mhtml_file, 'r', encoding='utf-8') as f:
        mhtml_data = f.read()
    msg = message_from_string(mhtml_data)
    html_content = None
    for part in msg.walk():
        if part.get_content_type() == 'text/html':
            html_content = part.get_payload(decode=True).decode('utf-8')
            break
    if not html_content:
        print(f"No HTML found in {mhtml_file}")
        return
    soup = BeautifulSoup(html_content, 'html.parser')
    structured_content = []
    for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li']):
        text = element.get_text().strip()
        if text:
            tag = element.name
            structured_content.append({'type': tag, 'text': text})
    print(f"Extracted {len(structured_content)} structured elements from {mhtml_file}")
    output_md_dir = Path(__file__).parent / "output" / "md"
    output_md_dir.mkdir(exist_ok=True)
    output_file = output_md_dir / (mhtml_file.stem + '.md')
    config_copy = config.copy()
    config_copy['output_file'] = str(output_file)
    create_corrected_md(structured_content, config_copy, client)

def create_corrected_md(structured_content, config, client):
    corrected_content = []
    all_changes = []
    for item in structured_content:
        item_type = item['type']
        original_text = item['text']
        corrections = get_corrections_from_llm(original_text, config, client)
        corrected_text = original_text
        changes_made = []
        for corr in sorted(corrections, key=lambda x: original_text.find(x['original']), reverse=True):
            orig = corr['original']
            corrected = corr['corrected']
            explanation = corr['explanation']
            pos = corrected_text.find(orig)
            if pos != -1:
                corrected_text = corrected_text[:pos] + "**" + corrected + "**" + corrected_text[pos + len(orig):]
                changes_made.append(f"{orig} -> {corrected}: {explanation}")
        all_changes.extend(changes_made)
        # Format based on type
        if item_type.startswith('h'):
            level = int(item_type[1])
            formatted = '#' * level + ' ' + corrected_text
        elif item_type == 'p':
            formatted = corrected_text
        elif item_type == 'li':
            formatted = '- ' + corrected_text
        else:
            formatted = corrected_text
        corrected_content.append(formatted)
    
    # Save as .md
    output_path = Path(config['output_file'])
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Corrected Web Content\n\n")
        f.write('\n\n'.join(corrected_content))
        if all_changes:
            f.write("\n\n## Changes Made\n\n")
            for change in all_changes:
                f.write(f"- {change}\n")
    print(f"Output saved to {output_path}")
    if all_changes:
        print("Changes:", all_changes)

def main():
    parser = argparse.ArgumentParser(description="Web Spell Checker: Download MHTML or Process to Corrected MD")
    parser.add_argument('mode', choices=['download', 'process', 'all'], help="Mode: 'download' to save MHTML from URLs, 'process' to correct existing MHTML files, 'all' to download missing and process all")
    args = parser.parse_args()

    config = load_config()
    workspace_dir = Path(__file__).parent
    input_dir = workspace_dir / 'input'
    input_dir.mkdir(exist_ok=True)
    output_mhtml_dir = workspace_dir / 'output' / 'mhtml'
    output_mhtml_dir.mkdir(exist_ok=True, parents=True)

    if args.mode == 'download':
        urls_file = input_dir / 'urls.txt'
        if not urls_file.exists():
            print(f"Create {urls_file} with one URL per line.")
            return
        with open(urls_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
        for url in urls:
            filename = re.sub(r'[^\w\-_.]', '_', url) + '.mhtml'
            mhtml_path = output_mhtml_dir / filename
            if mhtml_path.exists():
                print(f"Skipping {url}, file already exists.")
                continue
            save_mhtml(url, mhtml_path)
    elif args.mode == 'process':
        client = OpenAI(base_url="http://localhost:11434/v1", api_key="not-needed")
        for mhtml_file in output_mhtml_dir.glob('*.mhtml'):
            try:
                process_mhtml(mhtml_file, config, client)
            except Exception as e:
                print(f"Error processing {mhtml_file}: {e}")
    elif args.mode == 'all':
        urls_file = input_dir / 'urls.txt'
        if not urls_file.exists():
            print(f"Create {urls_file} with one URL per line.")
            return
        with open(urls_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
        for url in urls:
            filename = re.sub(r'[^\w\-_.]', '_', url) + '.mhtml'
            mhtml_path = output_mhtml_dir / filename
            if mhtml_path.exists():
                print(f"Skipping {url}, file already exists.")
                continue
            save_mhtml(url, mhtml_path)
        # Then process all
        client = OpenAI(base_url="http://localhost:11434/v1", api_key="not-needed")
        for mhtml_file in output_mhtml_dir.glob('*.mhtml'):
            try:
                process_mhtml(mhtml_file, config, client)
            except Exception as e:
                print(f"Error processing {mhtml_file}: {e}")

if __name__ == "__main__":
    main()