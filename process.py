import argparse
import sys
import time
from pathlib import Path
from datetime import datetime
from openai import OpenAI

from utils import load_config, save_config, log_performance_stats
from content_extractor import get_content_from_docx, get_content_from_mhtml
from document_processor import create_docx_output
from web_tools import download_url_as_mhtml


def select_model(client, default_model):
    """Lists available Ollama models and lets the user select one."""
    try:
        # The client.models.list() returns a SyncPage object. The list is in the .data attribute.
        models_response = client.models.list()
        if not models_response.data:
            print("No models found in Ollama. Please ensure models are installed.")
            return None
        
        # Each model object has an 'id' attribute with the model name.
        models = [m.id for m in models_response.data]
        
        print("\n--- 1. Model Selection ---")
        print("Available Ollama models:")
        default_index = -1
        for i, model_name in enumerate(models):
            if model_name == default_model:
                print(f"  {i+1}: {model_name} (default)")
                default_index = i
            else:
                print(f"  {i+1}: {model_name}")
        
        prompt = f"Select a model number to use (press Enter for default: {default_model}): "
        selection = input(prompt)

        if not selection.strip() and default_index != -1:
            return default_model
        
        try:
            index = int(selection) - 1
            if 0 <= index < len(models):
                return models[index]
            else:
                print("Invalid number. Using default.")
                return default_model
        except (ValueError, IndexError):
            if selection.strip():
                print("Invalid input. Using default.")
            return default_model

    except Exception as e:
        print(f"Could not fetch models from Ollama: {e}")
        return None

def select_source_files(workspace_dir):
    """Scans for all processable files and lets the user select them."""
    input_dir = workspace_dir / 'input'
    input_dir.mkdir(exist_ok=True)

    all_files = sorted(list(input_dir.glob("*.docx")) + list(input_dir.glob("*.mhtml")))

    if not all_files:
        print("\nNo processable files (.docx, .mhtml) found in 'input/'.")
        return []

    print("\n--- 3. Source Document Selection ---")
    print("Found the following processable files:")
    for i, f in enumerate(all_files):
        if "_corrected" in f.name: continue
        # Show relative path for clarity
        print(f"  {i+1}: {f.relative_to(workspace_dir).as_posix()}")

    print("\nEnter the numbers of the files to process (e.g., '1 3 4'), or 'all'. Press Enter to cancel.")
    selection = input("> ")

    if not selection.strip():
        print("No files selected. Exiting.")
        return []
    if selection.strip().lower() == 'all':
        return all_files
    
    selected_files = []
    try:
        indices = [int(i) - 1 for i in selection.split()]
        for i in sorted(list(set(indices))): # Process in order, no duplicates
            if 0 <= i < len(all_files):
                selected_files.append(all_files[i])
            else:
                print(f"Warning: Invalid number '{i+1}' ignored.")
    except ValueError:
        print("Invalid input. Please enter numbers separated by spaces.")
        return []
        
    return selected_files

def prompt_and_download_urls(workspace_dir):
    """Checks for urls.txt and prompts the user to download them as MHTML."""
    urls_file = workspace_dir / 'input' / 'urls.txt'
    if not urls_file.exists():
        return # No urls.txt, so nothing to do.

    print("\n--- Pre-Step: Download Web Pages ---")
    print(f"Found '{urls_file.relative_to(workspace_dir).as_posix()}'.")
    
    while True:
        import re
        choice = input("Do you want to download new web pages from this file? (y/n, default: n): ").lower().strip()
        if choice in ['y', 'yes']:
            should_download = True
            break
        elif choice in ['n', 'no', '']:
            should_download = False
            break
        else:
            print("Invalid input. Please enter 'y' or 'n'.")

    if not should_download:
        return

    mhtml_output_dir = workspace_dir / 'input'
    mhtml_output_dir.mkdir(exist_ok=True)

    with open(urls_file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    print(f"Found {len(urls)} URL(s) to process.")
    for url in urls:
        filename = re.sub(r'[^\w\-_.]', '_', url) + '.mhtml'
        mhtml_path = mhtml_output_dir / filename
        if mhtml_path.exists():
            print(f"Skipping download for '{url}', file already exists: {mhtml_path.name}")
            continue
        
        download_url_as_mhtml(url, mhtml_output_dir)

def run_interactive_wizard():
    """Guides the user through an interactive processing session."""
    print("--- Starting Interactive Spell-Check Wizard ---")
    
    config = load_config()
    workspace_dir = Path(__file__).parent

    # 0. (New) Prompt to download URLs
    prompt_and_download_urls(workspace_dir)

    # 1. Connect to Ollama and select model
    try:
        client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        selected_model = select_model(client, config['llm_model'])
        if not selected_model:
            return
        config['llm_model'] = selected_model
        print(f"Using model: {config['llm_model']}")
    except Exception as e:
        print("\nError: Could not connect to Ollama at http://localhost:11434.")
        print("Please ensure Ollama is running.")
        return

    # 2. Select source files
    files_to_process = select_source_files(workspace_dir)
    if not files_to_process:
        return

    # 3. Process selected files (Always DOCX)
    process_files(files_to_process, config, client, workspace_dir)

    # 4. Save choices for next time
    print("\nSaving choices for next run...")
    save_config({
        'llm_model': config['llm_model']
    })

    print("\n--- Wizard finished. ---")

def main():
    # If no arguments are passed, run the interactive wizard
    if len(sys.argv) == 1:
        run_interactive_wizard()
        return

    parser = argparse.ArgumentParser(
        description="A unified tool to process documents for spelling and grammar correction. Run without arguments for an interactive wizard.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""Examples:
  (Wizard Mode - Recommended)
    python process.py

  (Command-Line Mode)
  Process a single MHTML file:
    python process.py --source-type mhtml --input ./output/mhtml/some_page.mhtml

  Download and process a URL:
    python process.py --source-type url --input https://example.com
"""
    )
    parser.add_argument("--source-type", choices=['docx', 'mhtml', 'url'], required=True, help="The type of source to process.")
    parser.add_argument("--input", required=True, help="Path to a single input file or a URL (if --source-type is url).")
    args = parser.parse_args()

    config = load_config()
    workspace_dir = Path(__file__).parent

    try:
        # Add a check for the OpenAI client to ensure it's available
        client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        client.models.list() 
    except Exception as e:
        print("Error: Could not connect to Ollama at http://localhost:11434.")
        print("Please ensure Ollama is running and the model is available.")
        return

    files_to_process = []
    source_type_for_processing = args.source_type

    if args.input:
        if args.source_type == 'url':
            mhtml_output_dir = workspace_dir / 'input'
            mhtml_output_dir.mkdir(exist_ok=True)
            downloaded_file = download_url_as_mhtml(args.input, mhtml_output_dir)
            if downloaded_file:
                files_to_process.append(downloaded_file)
                source_type_for_processing = 'mhtml' # We now process the downloaded MHTML
        else:
            input_path = Path(args.input)
            if not input_path.is_file():
                print(f"Error: Input file not found at '{input_path}'")
                return
            files_to_process.append(input_path)
    else:
        # This case should not be reached if --input is required
        parser.print_help()
        return

    if not files_to_process:
        print("No files to process.")
        return

    process_files(files_to_process, config, client, workspace_dir, source_type_for_processing)

def process_files(files_to_process, config, client, workspace_dir, source_type_override=None):
    """Loops through a list of files and processes them."""
    output_dir = workspace_dir / config['output_dir']
    image_output_dir = output_dir / 'images'
    image_output_dir.mkdir(exist_ok=True)

    for file_path in files_to_process:
        print(f"\n--- Processing: {file_path.name} ---")
        doc_start_time = time.time()
        content = None
        source_type = source_type_override or file_path.suffix.lower().strip('.')
        
        if source_type == 'docx':
            content = get_content_from_docx(file_path)
        elif source_type == 'mhtml':
            content = get_content_from_mhtml(file_path, image_output_dir)

        if content:
            stats = {} # initialize
            output_path = output_dir / f"{file_path.stem}_corrected.docx"
            stats = create_docx_output(content, config, client, output_path)
            
            doc_end_time = time.time()
            total_doc_time = doc_end_time - doc_start_time
            
            model_used = config['llm_model']
            total_text_size = stats.get('total_text_size', 0)
            total_tokens_generated = stats.get('total_tokens_generated', 0)
            total_llm_time = stats.get('total_llm_time', 0)
            tokens_per_second = (total_tokens_generated / total_llm_time) if total_llm_time > 0 else 0
            
            print("\n--- Processing Summary ---")
            print(f"  Document:              {file_path.name}")
            print(f"  Total processing time: {total_doc_time:.2f} seconds")
            print(f"  Text size processed:   {total_text_size} characters")
            print(f"  Model used:            {model_used}")
            print(f"  LLM generation time:   {total_llm_time:.2f} seconds")
            print(f"  Tokens generated:      {total_tokens_generated}")
            print(f"  Average tokens/sec:    {tokens_per_second:.2f}")

            # Log performance stats to CSV
            try:
                log_data = {
                    'timestamp': datetime.now().isoformat(),
                    'document_name': file_path.name,
                    'model_used': model_used,
                    'total_doc_time': total_doc_time,
                    'total_text_size': total_text_size,
                    'total_llm_time': total_llm_time,
                    'total_tokens_generated': total_tokens_generated,
                    'tokens_per_second': tokens_per_second
                }
                log_file = output_dir / "performance_log.csv"
                log_performance_stats(log_file, log_data)
                print(f"  Performance stats logged to: {log_file.name}")
            except Exception as e:
                print(f"  [!] Could not write to performance log: {e}")
            print("--------------------------")
        else:
            print(f"Could not extract content from {file_path.name}. Skipping.")

if __name__ == "__main__":
    main()