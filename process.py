import argparse
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from openai import OpenAI, AzureOpenAI

from utils import load_config, save_config, log_performance_stats
from document_processor import process_docx
from web_tools import download_url_as_mhtml
try:
    from convert import mhtml_to_docx
except (ImportError, ModuleNotFoundError):
    mhtml_to_docx = None

OLLAMA_PROVIDER = "ollama"
AZURE_PROVIDER = "azure_openai"
AZURE_AI_FOUNDRY_PROVIDER = "azure_ai_foundry"


def prompt_course_folder(workspace_dir):
    """Prompts for a course folder under input/, selecting existing or creating a new one."""
    input_root = workspace_dir / 'input'
    input_root.mkdir(exist_ok=True)

    folders = sorted([d.name for d in input_root.iterdir() if d.is_dir()])

    print("\n--- 2. Course Folder ---")
    if folders:
        print("Existing input folders:")
        for i, folder_name in enumerate(folders, start=1):
            print(f"  {i}: {folder_name}")
    print("Enter a folder name/number (example: 1001).")

    while True:
        value = input("Course folder: ").strip()
        if not value:
            print("Course folder is required.")
            continue

        if value.isdigit():
            idx = int(value) - 1
            if 0 <= idx < len(folders):
                chosen = folders[idx]
                selected_dir = input_root / chosen
                print(f"Using existing folder: {chosen}")
                return chosen, selected_dir

        if any(ch in value for ch in ('/', '\\\\')):
            print("Invalid folder name. Do not use path separators.")
            continue

        chosen = value
        selected_dir = input_root / chosen
        if selected_dir.exists():
            print(f"Using existing folder: {chosen}")
        else:
            selected_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created folder: {chosen}")
        return chosen, selected_dir


def list_processable_files(source_dir):
    """Returns sorted processable files from a source folder."""
    return sorted(
        [f for f in source_dir.glob("*.docx") if "_corrected" not in f.name]
        + [f for f in source_dir.glob("*.mhtml") if "_corrected" not in f.name]
    )


def show_existing_files_for_course(workspace_dir, source_dir):
    """Displays files already present in the selected input course folder."""
    existing_files = sorted([p for p in source_dir.iterdir() if p.is_file()])
    if not existing_files:
        return

    print("\nFiles already in selected input folder:")
    for i, file_path in enumerate(existing_files, start=1):
        print(f"  {i}: {file_path.relative_to(workspace_dir).as_posix()}")


def normalize_provider(provider):
    """Normalizes persisted provider values to supported provider keys."""
    provider = (provider or "").strip().lower()
    if provider in {"azure", "azure_openai", "github"}:
        return AZURE_PROVIDER
    if provider in {"azure_ai_foundry", "foundry"}:
        return AZURE_AI_FOUNDRY_PROVIDER
    return OLLAMA_PROVIDER


def get_azure_settings(config):
    """Loads Azure OpenAI settings from env/config."""
    return {
        "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
        "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
        "api_version": os.getenv("AZURE_OPENAI_API_VERSION") or config.get("azure_api_version", "2024-10-21"),
        "deployment_name": config.get("azure_deployment_name", "").strip(),
    }


def get_azure_ai_foundry_settings(config):
    """Loads Azure AI Foundry settings from env/config."""
    return {
        "api_key": os.getenv("AZURE_AI_FOUNDRY_API_KEY"),
        "endpoint": os.getenv("AZURE_AI_FOUNDRY_ENDPOINT"),
        "model_name": config.get("azure_ai_foundry_model_name", "").strip(),
    }


def validate_provider_config(provider, config):
    """Validates provider-specific configuration before processing."""
    normalized_provider = normalize_provider(provider)
    if normalized_provider == AZURE_PROVIDER:
        azure_settings = get_azure_settings(config)
        if not azure_settings["deployment_name"]:
            raise RuntimeError("Missing Azure Deployment Name in configuration.")
    elif normalized_provider == AZURE_AI_FOUNDRY_PROVIDER:
        foundry_settings = get_azure_ai_foundry_settings(config)
        if not foundry_settings["model_name"]:
            raise RuntimeError("Missing Azure AI Foundry Model Name in configuration.")


def create_client(provider, config):
    """Creates an LLM client for the selected provider."""
    normalized_provider = normalize_provider(provider)
    if normalized_provider == AZURE_PROVIDER:
        azure_settings = get_azure_settings(config)
        if not azure_settings["api_key"]:
            raise RuntimeError("Missing AZURE_OPENAI_API_KEY environment variable.")
        if not azure_settings["endpoint"]:
            raise RuntimeError("Missing AZURE_OPENAI_ENDPOINT environment variable.")

        return AzureOpenAI(
            api_key=azure_settings["api_key"],
            azure_endpoint=azure_settings["endpoint"],
            api_version=azure_settings["api_version"],
        )
    elif normalized_provider == AZURE_AI_FOUNDRY_PROVIDER:
        foundry_settings = get_azure_ai_foundry_settings(config)
        if not foundry_settings["api_key"]:
            raise RuntimeError("Missing AZURE_AI_FOUNDRY_API_KEY environment variable.")
        if not foundry_settings["endpoint"]:
            raise RuntimeError("Missing AZURE_AI_FOUNDRY_ENDPOINT environment variable.")

        return OpenAI(
            api_key=foundry_settings["api_key"],
            base_url=foundry_settings["endpoint"].rstrip("/"),
        )

    return OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")


def fetch_ollama_models():
    """Fetches available model IDs from Ollama, returning an empty list on failure."""
    try:
        client = create_client(OLLAMA_PROVIDER, {})
        models_response = client.models.list()
        return [m.id for m in models_response.data] if models_response.data else []
    except Exception as e:
        print(f"Could not fetch models from Ollama: {e}")
        return []


def select_model(default_model, default_provider, config):
    """Lists available models and lets the user select provider/model."""
    models = fetch_ollama_models()
    options = [(OLLAMA_PROVIDER, model_name) for model_name in models]
    
    azure_settings = get_azure_settings(config)
    if azure_settings["deployment_name"]:
        options.append((AZURE_PROVIDER, azure_settings["deployment_name"]))
    
    foundry_settings = get_azure_ai_foundry_settings(config)
    if foundry_settings["model_name"]:
        options.append((AZURE_AI_FOUNDRY_PROVIDER, foundry_settings["model_name"]))
    
    if not models and not azure_settings["deployment_name"] and not foundry_settings["model_name"]:
        print("No models found. Ensure Ollama is running and/or configure Azure provider.")
    elif not models:
        print("No models found in Ollama. Azure providers are available if configured.")

    try:
        print("\n--- 1. Model Selection ---")
        print("Available models:")
        default_index = -1
        normalized_default_provider = normalize_provider(default_provider)
        for i, (provider, model_name) in enumerate(options):
            if provider == AZURE_PROVIDER:
                provider_label = "Azure OpenAI"
            elif provider == AZURE_AI_FOUNDRY_PROVIDER:
                provider_label = "Azure AI Foundry"
            else:
                provider_label = "Ollama"
            label = f"{model_name} ({provider_label})"
            if model_name == default_model and provider == normalized_default_provider:
                print(f"  {i+1}: {label} (default)")
                default_index = i
            else:
                print(f"  {i+1}: {label}")

        default_label = default_model
        if normalized_default_provider == AZURE_PROVIDER:
            default_label = f"{default_model} (Azure OpenAI)"
        elif normalized_default_provider == AZURE_AI_FOUNDRY_PROVIDER:
            default_label = f"{default_model} (Azure AI Foundry)"
        elif default_model:
            default_label = f"{default_model} (Ollama)"

        prompt = f"Select a model number to use (press Enter for default: {default_label}): "
        selection = input(prompt)

        if not selection.strip() and default_index != -1:
            return options[default_index]
        if not selection.strip() and options:
            print("Default model was not available. Using first listed option.")
            return options[0]

        try:
            index = int(selection) - 1
            if 0 <= index < len(options):
                return options[index]
            else:
                print("Invalid number. Using default.")
                return normalized_default_provider, default_model
        except (ValueError, IndexError):
            if selection.strip():
                print("Invalid input. Using default.")
            return normalized_default_provider, default_model
    except Exception:
        return normalize_provider(default_provider), default_model


def format_model_label(model_name, provider):
    """Returns a user-friendly model label including provider."""
    normalized_provider = normalize_provider(provider)
    if normalized_provider == AZURE_PROVIDER:
        provider_label = "Azure OpenAI"
    elif normalized_provider == AZURE_AI_FOUNDRY_PROVIDER:
        provider_label = "Azure AI Foundry"
    else:
        provider_label = "Ollama"
    return f"{model_name} ({provider_label})"


def prompt_change_model(current_model, current_provider):
    """Asks whether to keep the last used model or choose another one."""
    print("\n--- 1. AI Model ---")
    print(f"Last used model: {format_model_label(current_model, current_provider)}")
    while True:
        choice = input("Change model for this run? (y/n, default: n): ").lower().strip()
        if choice in ['y', 'yes']:
            return True
        if choice in ['n', 'no', '']:
            return False
        print("Invalid input. Please enter 'y' or 'n'.")

def select_source_files(workspace_dir, source_dir):
    """Scans for processable files in source_dir and lets the user select them."""
    all_files = list_processable_files(source_dir)

    if not all_files:
        print(f"\nNo processable files (.docx, .mhtml) found in '{source_dir.relative_to(workspace_dir).as_posix()}'.")
        return []

    print("\n--- 3. Source Document Selection ---")
    print(f"Found the following processable files in '{source_dir.relative_to(workspace_dir).as_posix()}':")
    for i, f in enumerate(all_files):
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

def prompt_should_download(urls_file):
    """Asks whether urls.txt should be downloaded in this run."""
    if not urls_file.exists():
        return False

    print("\n--- 4. Download Web Pages ---")
    print(f"Found '{urls_file.as_posix()}'.")
    while True:
        choice = input("Download web pages from this file? (y/n, default: n): ").lower().strip()
        if choice in ['y', 'yes']:
            return True
        if choice in ['n', 'no', '']:
            return False
        print("Invalid input. Please enter 'y' or 'n'.")


def prompt_process_strategy(after_download):
    """Asks whether to process all files immediately or choose file selection later."""
    print("\n--- 5. Processing Strategy ---")
    if after_download:
        print("You chose to download pages in this run.")
        question = "Process all files in the selected course folder after download? (y/n, default: y): "
    else:
        print("No download step selected.")
        question = "Process all files in the selected course folder now? (y/n, default: n): "

    while True:
        choice = input(question).lower().strip()
        if after_download:
            if choice in ['y', 'yes', '']:
                return 'all'
            if choice in ['n', 'no']:
                return 'choose_later'
        else:
            if choice in ['y', 'yes']:
                return 'all'
            if choice in ['n', 'no', '']:
                return 'choose_later'
        print("Invalid input. Please enter 'y' or 'n'.")


def download_urls_to_folder(urls_file, mhtml_output_dir):
    """Downloads URLs from urls.txt into a selected course folder."""
    with open(urls_file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    print(f"Found {len(urls)} URL(s) to process.")
    downloaded_files = []
    for url in urls:
        downloaded = download_url_as_mhtml(url, mhtml_output_dir)
        if downloaded:
            downloaded_files.append(downloaded)
    return downloaded_files

def run_interactive_wizard():
    """Guides the user through an interactive processing session."""
    print("--- Starting Interactive Spell-Check Wizard ---")
    
    config = load_config()
    config['llm_provider'] = normalize_provider(config.get('llm_provider', OLLAMA_PROVIDER))
    if config['llm_provider'] == AZURE_PROVIDER:
        azure_settings = get_azure_settings(config)
        if azure_settings['deployment_name']:
            config['llm_model'] = azure_settings['deployment_name']
    elif config['llm_provider'] == AZURE_AI_FOUNDRY_PROVIDER:
        foundry_settings = get_azure_ai_foundry_settings(config)
        if foundry_settings['model_name']:
            config['llm_model'] = foundry_settings['model_name']

    workspace_dir = Path(__file__).parent

    # 1. Choose/create course folder first
    selected_course, source_dir = prompt_course_folder(workspace_dir)
    show_existing_files_for_course(workspace_dir, source_dir)

    # 2. Optionally change model, otherwise keep last used model
    selected_provider = normalize_provider(config.get('llm_provider', OLLAMA_PROVIDER))
    should_change_model = prompt_change_model(config['llm_model'], selected_provider)
    try:
        if should_change_model:
            selected_provider, selected_model = select_model(
                config['llm_model'],
                config.get('llm_provider', OLLAMA_PROVIDER),
                config,
            )
            config['llm_provider'] = normalize_provider(selected_provider)
            config['llm_model'] = selected_model
            if config['llm_provider'] == AZURE_PROVIDER:
                config['llm_model'] = get_azure_settings(config)['deployment_name'] or selected_model
            elif config['llm_provider'] == AZURE_AI_FOUNDRY_PROVIDER:
                config['llm_model'] = get_azure_ai_foundry_settings(config)['model_name'] or selected_model
        else:
            config['llm_provider'] = selected_provider

        validate_provider_config(config['llm_provider'], config)
        client = create_client(config['llm_provider'], config)
        print(f"Using model: {format_model_label(config['llm_model'], config['llm_provider'])}")
    except Exception as e:
        print(f"\nError: Could not initialize {selected_provider} client: {e}")
        if selected_provider == AZURE_PROVIDER:
            print("Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT, and configure Azure Deployment Name.")
        elif selected_provider == AZURE_AI_FOUNDRY_PROVIDER:
            print("Set AZURE_AI_FOUNDRY_API_KEY and AZURE_AI_FOUNDRY_ENDPOINT, and configure Azure AI Foundry Model Name.")
        else:
            print("Please ensure Ollama is running and a model is available.")
        return

    # 3. Ask remaining wizard questions before running
    urls_file = workspace_dir / 'input' / 'urls.txt'
    should_download = prompt_should_download(urls_file)
    process_strategy = prompt_process_strategy(should_download)

    output_dir = workspace_dir / config['output_dir'] / selected_course
    output_dir.mkdir(parents=True, exist_ok=True)

    # 3. Execute download after all main choices are made
    if should_download:
        print(f"\nDownloading to '{source_dir.relative_to(workspace_dir).as_posix()}'...")
        downloaded_files = download_urls_to_folder(urls_file, source_dir)
    else:
        downloaded_files = []

    # 4. Select files only if user asked to choose later
    if process_strategy == 'choose_later':
        files_to_process = select_source_files(workspace_dir, source_dir)
    elif should_download:
        files_to_process = list_processable_files(source_dir)
        if not files_to_process:
            print("\nNo files were downloaded to process.")
    else:
        files_to_process = list_processable_files(source_dir)
        if not files_to_process:
            print(f"\nNo processable files found in '{source_dir.relative_to(workspace_dir).as_posix()}'.")

    if not files_to_process:
        return

    # 5. Process selected files
    process_files(files_to_process, config, client, workspace_dir, output_dir=output_dir, cleanup_temp_docx=True)

    # 4. Save choices for next time
    print("\nSaving choices for next run...")
    save_config({
        'llm_provider': config['llm_provider'],
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
    config['llm_provider'] = normalize_provider(config.get('llm_provider', OLLAMA_PROVIDER))
    if config['llm_provider'] == AZURE_PROVIDER:
        azure_settings = get_azure_settings(config)
        if azure_settings['deployment_name']:
            config['llm_model'] = azure_settings['deployment_name']
    elif config['llm_provider'] == AZURE_AI_FOUNDRY_PROVIDER:
        foundry_settings = get_azure_ai_foundry_settings(config)
        if foundry_settings['model_name']:
            config['llm_model'] = foundry_settings['model_name']

    workspace_dir = Path(__file__).parent

    try:
        provider = config.get('llm_provider', OLLAMA_PROVIDER)
        validate_provider_config(provider, config)
        client = create_client(provider, config)
        if provider == OLLAMA_PROVIDER:
            client.models.list()
    except Exception as e:
        provider = config.get('llm_provider', OLLAMA_PROVIDER)
        print(f"Error: Could not initialize {provider} client: {e}")
        if provider == AZURE_PROVIDER:
            print("Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT, and configure Azure Deployment Name.")
        elif provider == AZURE_AI_FOUNDRY_PROVIDER:
            print("Set AZURE_AI_FOUNDRY_API_KEY and AZURE_AI_FOUNDRY_ENDPOINT, and configure Azure AI Foundry Model Name.")
        else:
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

def process_files(files_to_process, config, client, workspace_dir, source_type_override=None, output_dir=None, cleanup_temp_docx=False):
    """Loops through a list of files and processes them."""
    output_dir = output_dir or (workspace_dir / config['output_dir'])
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_docx_files = []

    for file_path in files_to_process:
        print(f"\n--- Processing: {file_path.name} ---")
        doc_start_time = time.time()
        
        processing_file_path = file_path
        source_type = source_type_override or file_path.suffix.lower().strip('.')
        
        if source_type == 'mhtml':
            if mhtml_to_docx is None:
                print("  [!] MHTML to DOCX conversion is unavailable.")
                print("      This feature requires 'pywin32' (Windows only) and MS Word.")
                print("      To install, run: pip install pywin32")
                print(f"      Skipping file: {file_path.name}")
                continue

            print(f"  -> Converting MHTML to DOCX using MS Word...")
            converted_docx_path = file_path.with_suffix('.from_mhtml.docx')
            try:
                mhtml_to_docx(str(file_path), str(converted_docx_path))
                processing_file_path = converted_docx_path
                temp_docx_files.append(converted_docx_path)
                print(f"  -> Conversion successful. Now processing: {processing_file_path.name}")
            except Exception as e:
                print(f"  [!] MHTML to DOCX conversion failed: {e}")
                print(f"      Ensure MS Word is installed and 'win32com' is working.")
                print(f"      Skipping file: {file_path.name}")
                continue

        # Process the DOCX file directly
        stats = {} # initialize
        output_path = output_dir / f"{file_path.stem}_corrected.docx"
        
        stats = process_docx(str(processing_file_path), str(output_path), config, client)
        
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
            log_file = workspace_dir / config['output_dir'] / "performance_log.csv"
            log_performance_stats(log_file, log_data)
            print(f"  Performance stats logged to: {log_file.name}")
        except Exception as e:
            print(f"  [!] Could not write to performance log: {e}")
        print("--------------------------")

    if cleanup_temp_docx:
        for temp_file in temp_docx_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    print(f"  -> Cleaned up temporary file: {temp_file.name}")
            except Exception as e:
                print(f"  [!] Could not remove temporary file '{temp_file.name}': {e}")

if __name__ == "__main__":
    main()