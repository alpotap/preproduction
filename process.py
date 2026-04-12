"""Main entry point for document processing, model selection, and output generation."""

import argparse
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from openai import OpenAI, AzureOpenAI

from utils import load_config, save_config, log_performance_stats
from document_processor import build_correction_plan, apply_inline_correction_plan, apply_hybrid_correction_plan, process_docx
from web_tools import download_url_as_mhtml
try:
    from prompts import PROMPT_DEFINITIONS, DEFAULT_PROMPT_KEY, get_prompt_abbreviation
except (ImportError, ModuleNotFoundError):
    DEFAULT_PROMPT_KEY = "default"
    PROMPT_DEFINITIONS = {
        "default": {
            "name": "Default",
            "summary": "General spelling and grammar correction.",
        }
    }

    def get_prompt_abbreviation(prompt_key, fallback="GEN"):
        return fallback
try:
    from tracked_processor import process_docx_tracked, process_docx_tracked_with_plan
except (ImportError, ModuleNotFoundError):
    process_docx_tracked = None
    process_docx_tracked_with_plan = None
try:
    from convert import mhtml_to_docx, pdf_to_docx
except (ImportError, ModuleNotFoundError):
    mhtml_to_docx = None
    pdf_to_docx = None
try:
    from consistency_full_tool import run_full_consistency
except (ImportError, ModuleNotFoundError):
    run_full_consistency = None

OLLAMA_PROVIDER = "ollama"
LM_STUDIO_PROVIDER = "lm_studio"
AZURE_PROVIDER = "azure_openai"
AZURE_AI_FOUNDRY_PROVIDER = "azure_ai_foundry"

OUTPUT_TYPE_REGISTRY = {
    "inline": {
        "label": "Inline (with comments)",
        "suffix": "corrected_inline.docx",
    },
    "uncommented": {
        "label": "Inline (no comments)",
        "suffix": "corrected_uncommented.docx",
    },
    "track_changes": {
        "label": "Track Changes",
        "suffix": "corrected_track_changes.docx",
    },
    "hybrid": {
        "label": "Hybrid (inline + Word comments)",
        "suffix": "corrected_hybrid.docx",
    },
}
DEFAULT_OUTPUT_TYPES = ["inline", "track_changes", "hybrid"]


def normalize_output_types(output_types):
    """Return valid output types in registry order; fallback to defaults."""
    if isinstance(output_types, str):
        requested = [x.strip().lower() for x in output_types.split(',') if x.strip()]
    elif isinstance(output_types, (list, tuple, set)):
        requested = [str(x).strip().lower() for x in output_types if str(x).strip()]
    else:
        requested = []

    requested_set = set(requested)
    normalized = [key for key in OUTPUT_TYPE_REGISTRY if key in requested_set]
    if not normalized:
        return list(DEFAULT_OUTPUT_TYPES)
    return normalized


def serialize_output_types(output_types):
    """Serialize selected output types for config persistence."""
    return ", ".join(normalize_output_types(output_types))


def format_output_types(output_types):
    """Human-readable labels for selected output types."""
    selected = normalize_output_types(output_types)
    return ", ".join(OUTPUT_TYPE_REGISTRY[key]["label"] for key in selected)


def prompt_course_folder(workspace_dir):
    """Prompts for a course folder under input/, selecting existing or creating a new one."""
    input_root = workspace_dir / 'input'
    input_root.mkdir(exist_ok=True)

    folders = sorted([d.name for d in input_root.iterdir() if d.is_dir()])

    print("\n---Enter Course Number (Folder) ---")
    if folders:
        print("Existing courses and folders:")
        for i, folder_name in enumerate(folders, start=1):
            print(f"  {i}: {folder_name}")
    print("Enter a course/folder name/number (example: 1001). A new number will create new directory under 'input/'.")

    while True:
        value = input("Course folder: ").strip()
        if not value:
            print("Course number is required.")
            continue

        if value.isdigit():
            idx = int(value) - 1
            if 0 <= idx < len(folders):
                chosen = folders[idx]
                selected_dir = input_root / chosen
                print(f"Using existing course: {chosen}")
                return chosen, selected_dir

        if any(ch in value for ch in ('/', '\\\\')):
            print("Invalid course name. Do not use path separators.")
            continue

        chosen = value
        selected_dir = input_root / chosen
        if selected_dir.exists():
            print(f"Using existing course folder: {chosen}")
        else:
            selected_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created folder: {chosen}")
        return chosen, selected_dir


def list_processable_files(source_dir):
    """Returns sorted processable files from a source folder."""
    return sorted(
        [
            f
            for f in source_dir.glob("*.docx")
            if "_corrected" not in f.name
        ]
        + [f for f in source_dir.glob("*.mhtml") if "_corrected" not in f.name]
        + [f for f in source_dir.glob("*.pdf")]
    )


def build_output_stem(file_path):
    """Returns a stable output stem without conversion-source suffixes."""
    stem = file_path.stem
    for suffix in (".from_mhtml", ".from_pdf"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem


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
    if provider in {"lm_studio", "lmstudio", "local", "local_lm_studio"}:
        return LM_STUDIO_PROVIDER
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


def get_lm_studio_settings(config):
    """Loads LM Studio settings from env/config."""
    base_url = (
        os.getenv("LM_STUDIO_BASE_URL")
        or config.get("lm_studio_base_url", "http://127.0.0.1:1234/v1")
    ).strip()
    if base_url and not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"
    return {
        "base_url": base_url.rstrip("/"),
        "model_name": config.get("lm_studio_model_name", "").strip(),
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
    elif normalized_provider == LM_STUDIO_PROVIDER:
        if not config.get('llm_model', '').strip():
            raise RuntimeError("Missing LM Studio model selection. Choose a model from the wizard.")


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
    elif normalized_provider == LM_STUDIO_PROVIDER:
        lm_studio_settings = get_lm_studio_settings(config)
        if not lm_studio_settings["base_url"]:
            raise RuntimeError("Missing LM Studio base URL in configuration.")
        return OpenAI(
            api_key=os.getenv("LM_STUDIO_API_KEY", "lm-studio"),
            base_url=lm_studio_settings["base_url"],
        )

    return OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")


def fetch_ollama_models():
    """Fetches available model IDs from Ollama, returning an empty list on failure.
    
    Developer note: Each model object contains id, context, and other metadata fields.
    We extract only the 'id' for user-facing display.
    """
    try:
        client = create_client(OLLAMA_PROVIDER, {})
        models_response = client.models.list()
        # Extract only model.id for user display; id and context fields available in raw objects
        return [m.id for m in models_response.data] if models_response.data else []
    except Exception as e:
        print(f"Could not fetch models from Ollama: {e}")
        return []


def fetch_lm_studio_models(config):
    """Fetches available model IDs from LM Studio, returning an empty list on failure."""
    try:
        client = create_client(LM_STUDIO_PROVIDER, config)
        models_response = client.models.list()
        return [m.id for m in models_response.data] if models_response.data else []
    except Exception as e:
        print(f"Could not fetch models from LM Studio: {e}")
        return []


def select_model(default_model, default_provider, config):
    """Lists available models and lets the user select provider/model."""
    ollama_models = fetch_ollama_models()
    lm_studio_models = fetch_lm_studio_models(config)
    options = [(OLLAMA_PROVIDER, model_name) for model_name in ollama_models]
    options.extend((LM_STUDIO_PROVIDER, model_name) for model_name in lm_studio_models)
    
    azure_settings = get_azure_settings(config)
    if azure_settings["deployment_name"]:
        options.append((AZURE_PROVIDER, azure_settings["deployment_name"]))
    
    foundry_settings = get_azure_ai_foundry_settings(config)
    if foundry_settings["model_name"]:
        options.append((AZURE_AI_FOUNDRY_PROVIDER, foundry_settings["model_name"]))
    
    lm_studio_settings = get_lm_studio_settings(config)
    if lm_studio_models:
        print(f"LM Studio server reachable at {lm_studio_settings['base_url']}; model(s): {', '.join(lm_studio_models)}")
    else:
        print(f"LM Studio unavailable or has no loaded model at {lm_studio_settings['base_url']}.")

    if not ollama_models and not lm_studio_models and not azure_settings["deployment_name"] and not foundry_settings["model_name"]:
        print("No models found. Ensure Ollama/LM Studio is running and/or configure Azure provider.")
    elif not ollama_models and not lm_studio_models:
        print("No models found in local providers (Ollama/LM Studio). Azure providers are available if configured.")

    try:
        print("\n--- Model Selection ---")
        print("Available models:")
        default_index = -1
        normalized_default_provider = normalize_provider(default_provider)
        # Display only model name to users (id and context fields kept internal for developers)
        for i, (provider, model_name) in enumerate(options):
            if provider == AZURE_PROVIDER:
                provider_label = "Azure OpenAI"
            elif provider == AZURE_AI_FOUNDRY_PROVIDER:
                provider_label = "Azure AI Foundry"
            elif provider == LM_STUDIO_PROVIDER:
                provider_label = "LM Studio"
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
        elif normalized_default_provider == LM_STUDIO_PROVIDER:
            default_label = f"{default_model} (LM Studio)"
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
    elif normalized_provider == LM_STUDIO_PROVIDER:
        provider_label = "LM Studio"
    else:
        provider_label = "Ollama"
    return f"{model_name} ({provider_label})"


def prompt_change_model(current_model, current_provider):
    """Asks whether to keep the last used model or choose another one."""
    print("\n--- AI Model ---")
    print(f"Last used model: {format_model_label(current_model, current_provider)}")
    while True:
        choice = input("Change model for this run? (y/n, default: n): ").lower().strip()
        if choice in ['y', 'yes']:
            return True
        if choice in ['n', 'no', '']:
            return False
        print("Invalid input. Please enter 'y' or 'n'.")


def normalize_prompt_key(prompt_key):
    """Returns a valid prompt key, falling back to DEFAULT_PROMPT_KEY."""
    if prompt_key in PROMPT_DEFINITIONS:
        return prompt_key
    return DEFAULT_PROMPT_KEY if DEFAULT_PROMPT_KEY in PROMPT_DEFINITIONS else next(iter(PROMPT_DEFINITIONS.keys()))


def prompt_select_prompt_type(current_prompt_key):
    """Lets the user select the prompt type shown by name and summary."""
    print("\n--- Prompt Type ---")

    options = list(PROMPT_DEFINITIONS.items())
    default_key = normalize_prompt_key(current_prompt_key)
    default_meta = PROMPT_DEFINITIONS.get(default_key, {})
    default_label = default_meta.get('name', default_key)

    for i, (prompt_key, meta) in enumerate(options, start=1):
        name = meta.get('name', prompt_key)
        summary = meta.get('summary', '')
        suffix = " (default)" if prompt_key == default_key else ""
        print(f"  {i}: {name}{suffix}")
        if summary:
            print(f"     {summary}")

    selection = input(f"Select prompt type number (press Enter for default: {default_label}): ").strip()
    if not selection:
        return default_key

    try:
        index = int(selection) - 1
        if 0 <= index < len(options):
            return options[index][0]
    except ValueError:
        pass

    print("Invalid input. Using default prompt type.")
    return default_key


def prompt_level_a_task():
    """Level A menu for selecting high-level task."""
    print("\n--- Level A: Select A Task ---")
    print("  1: Process files")
    print("  2: Download and process files")
    print("  3: Change LLM provider/model")
    print("  4: Run cross-document consistency analysis")
    print("  5: Select output types")

    while True:
        choice = input("Choose task number (1/2/3/4/5): ").strip()
        if choice in {"1", "2", "3", "4", "5"}:
            return choice
        print("Invalid input. Enter one of: 1, 2, 3, 4, 5.")


def prompt_select_output_types(current_output_types):
    """Prompt user for multi-select output types; returns normalized key list."""
    current = normalize_output_types(current_output_types)
    options = list(OUTPUT_TYPE_REGISTRY.items())

    print("\n--- Output Types ---")
    print("Select one or more output types by number (example: 1 3 4).")
    print("Type 'all' to select all output types. Press Enter to keep current selection.")
    print("Current selection:")
    for key in current:
        print(f"  - {OUTPUT_TYPE_REGISTRY[key]['label']} [{key}]")

    print("\nAvailable output types:")
    for idx, (key, meta) in enumerate(options, start=1):
        selected_marker = "x" if key in current else " "
        print(f"  {idx}: [{selected_marker}] {meta['label']} ({key})")

    while True:
        raw = input("Select output types: ").strip().lower()
        if not raw:
            return current
        if raw == "all":
            return list(OUTPUT_TYPE_REGISTRY.keys())

        try:
            picked_indices = sorted(set(int(part) - 1 for part in raw.split()))
        except ValueError:
            print("Invalid input. Enter numbers separated by spaces, or 'all'.")
            continue

        selected = []
        for i in picked_indices:
            if 0 <= i < len(options):
                selected.append(options[i][0])
            else:
                print(f"Invalid selection '{i+1}' ignored.")

        selected = normalize_output_types(selected)
        if selected:
            return selected

        print("At least one output type must be selected.")


def prompt_level_d_file_selection(workspace_dir, source_dir):
    """Level D file selection: all files or a numeric list."""
    all_files = list_processable_files(source_dir)
    if not all_files:
        print(f"\nNo processable files (.docx, .mhtml, .pdf) found in '{source_dir.relative_to(workspace_dir).as_posix()}'.")
        return []

    print("\n--- Level D: Select Files ---")
    print(f"Found the following processable files in '{source_dir.relative_to(workspace_dir).as_posix()}':")
    for i, f in enumerate(all_files, start=1):
        print(f"  {i}: {f.relative_to(workspace_dir).as_posix()}")

    print("\nEnter 'all' to process all files, or enter numbers like '1 2 3'. Press Enter to cancel.")
    selection = input("> ").strip().lower()
    if not selection:
        print("No files selected. Exiting.")
        return []
    if selection == 'all':
        return all_files

    selected_files = []
    try:
        indices = [int(i) - 1 for i in selection.split()]
        for i in sorted(set(indices)):
            if 0 <= i < len(all_files):
                selected_files.append(all_files[i])
            else:
                print(f"Warning: Invalid number '{i+1}' ignored.")
    except ValueError:
        print("Invalid input. Please enter 'all' or numbers separated by spaces.")
        return []

    return selected_files

def select_source_files(workspace_dir, source_dir):
    """Scans for processable files in source_dir and lets the user select them."""
    all_files = list_processable_files(source_dir)

    if not all_files:
        print(f"\nNo processable files (.docx, .mhtml, .pdf) found in '{source_dir.relative_to(workspace_dir).as_posix()}'.")
        return []

    print("\n--- Source Document Selection ---")
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

    print("\n--- Download Web Pages ---")
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
    print("\n--- Processing Strategy ---")
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
    config['active_prompt'] = normalize_prompt_key(config.get('active_prompt', DEFAULT_PROMPT_KEY))
    config['output_types'] = normalize_output_types(config.get('output_types', DEFAULT_OUTPUT_TYPES))
    if config['llm_provider'] == AZURE_PROVIDER:
        azure_settings = get_azure_settings(config)
        if azure_settings['deployment_name']:
            config['llm_model'] = azure_settings['deployment_name']
    elif config['llm_provider'] == AZURE_AI_FOUNDRY_PROVIDER:
        foundry_settings = get_azure_ai_foundry_settings(config)
        if foundry_settings['model_name']:
            config['llm_model'] = foundry_settings['model_name']
    elif config['llm_provider'] == LM_STUDIO_PROVIDER:
        lm_studio_settings = get_lm_studio_settings(config)
        if lm_studio_settings['model_name']:
            config['llm_model'] = lm_studio_settings['model_name']

    workspace_dir = Path(__file__).parent
    run_consistency_only = False

    while True:
        task_key = prompt_level_a_task()

        if task_key == '3':
            previous_provider = config['llm_provider']
            previous_model = config['llm_model']

            selected_provider, selected_model = select_model(
                config['llm_model'],
                config.get('llm_provider', OLLAMA_PROVIDER),
                config,
            )
            selected_provider = normalize_provider(selected_provider)

            config['llm_provider'] = selected_provider
            config['llm_model'] = selected_model
            if config['llm_provider'] == AZURE_PROVIDER:
                config['llm_model'] = get_azure_settings(config)['deployment_name'] or selected_model
            elif config['llm_provider'] == AZURE_AI_FOUNDRY_PROVIDER:
                config['llm_model'] = get_azure_ai_foundry_settings(config)['model_name'] or selected_model
            elif config['llm_provider'] == LM_STUDIO_PROVIDER:
                config['llm_model'] = selected_model
                config['lm_studio_model_name'] = selected_model

            try:
                validate_provider_config(config['llm_provider'], config)
                client = create_client(config['llm_provider'], config)
                if config['llm_provider'] in {OLLAMA_PROVIDER, LM_STUDIO_PROVIDER}:
                    client.models.list()
                save_config({
                    'llm_provider': config['llm_provider'],
                    'llm_model': config['llm_model'],
                    'lm_studio_model_name': config.get('lm_studio_model_name', ''),
                    'active_prompt': config['active_prompt']
                })
                print(f"Saved model: {format_model_label(config['llm_model'], config['llm_provider'])}")
            except Exception as e:
                config['llm_provider'] = previous_provider
                config['llm_model'] = previous_model
                print(f"\nError: Could not initialize {selected_provider} client: {e}")
                if selected_provider == AZURE_PROVIDER:
                    print("Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT, and configure Azure Deployment Name.")
                elif selected_provider == AZURE_AI_FOUNDRY_PROVIDER:
                    print("Set AZURE_AI_FOUNDRY_API_KEY and AZURE_AI_FOUNDRY_ENDPOINT, and configure Azure AI Foundry Model Name.")
                elif selected_provider == LM_STUDIO_PROVIDER:
                    print("Ensure LM Studio local server is running and at least one model is loaded.")
                else:
                    print("Please ensure Ollama is running and a model is available.")

            print("Returning to Level A menu...")
            continue

        if task_key == '5':
            config['output_types'] = prompt_select_output_types(config.get('output_types', DEFAULT_OUTPUT_TYPES))
            save_config({
                'output_types': serialize_output_types(config['output_types'])
            })
            print(f"Saved output types: {format_output_types(config['output_types'])}")
            print("Returning to Level A menu...")
            continue

        run_download = (task_key == '2')
        run_consistency_only = (task_key == '4')
        break

    try:
        validate_provider_config(config['llm_provider'], config)
        client = create_client(config['llm_provider'], config)
        print(f"Using model: {format_model_label(config['llm_model'], config['llm_provider'])}")
    except Exception as e:
        provider = config['llm_provider']
        print(f"\nError: Could not initialize {provider} client: {e}")
        if provider == AZURE_PROVIDER:
            print("Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT, and configure Azure Deployment Name.")
        elif provider == AZURE_AI_FOUNDRY_PROVIDER:
            print("Set AZURE_AI_FOUNDRY_API_KEY and AZURE_AI_FOUNDRY_ENDPOINT, and configure Azure AI Foundry Model Name.")
        elif provider == LM_STUDIO_PROVIDER:
            print("Ensure LM Studio local server is running and at least one model is loaded.")
        else:
            print("Please ensure Ollama is running and a model is available.")
        return

    print("\n--- Level B: Select Or Create Folder ---")
    selected_course, source_dir = prompt_course_folder(workspace_dir)
    show_existing_files_for_course(workspace_dir, source_dir)

    if run_consistency_only:
        if run_full_consistency is None:
            print("\nConsistency tools are unavailable. Ensure consistency_full_tool.py is present.")
            return

        consistency_output_dir = workspace_dir / config['output_dir'] / selected_course / "consistency"
        consistency_docx = consistency_output_dir / "consistency_analysis.docx"
        print(f"\nRunning cross-document consistency analysis for '{source_dir.relative_to(workspace_dir).as_posix()}'...")

        try:
            results = run_full_consistency(source_dir, consistency_output_dir, consistency_docx)
            print("\n--- Consistency Analysis Completed ---")
            print(f"Documents scanned: {results['document_count']}")
            print(f"Metadata JSON: {Path(results['metadata_json']).relative_to(workspace_dir).as_posix()}")
            print(f"Documents CSV: {Path(results['documents_csv']).relative_to(workspace_dir).as_posix()}")
            print(f"Keywords CSV: {Path(results['keywords_csv']).relative_to(workspace_dir).as_posix()}")
            print(f"Product names CSV: {Path(results['product_names_csv']).relative_to(workspace_dir).as_posix()}")
            print(f"Analysis DOCX: {Path(results['analysis_docx']).relative_to(workspace_dir).as_posix()}")
            print(f"Model used: {results['model_used']} ({results['provider_used']})")
        except Exception as e:
            print(f"\nConsistency analysis failed: {e}")
        return

    print("\n--- Level C: Select Prompt Type ---")
    config['active_prompt'] = prompt_select_prompt_type(config.get('active_prompt', DEFAULT_PROMPT_KEY))
    selected_prompt = PROMPT_DEFINITIONS.get(config['active_prompt'], {})
    print(f"Using prompt: {selected_prompt.get('name', config['active_prompt'])} [{config['active_prompt']}]")
    save_config({
        'llm_provider': config['llm_provider'],
        'llm_model': config['llm_model'],
        'lm_studio_model_name': config.get('lm_studio_model_name', ''),
        'active_prompt': config['active_prompt'],
        'output_types': serialize_output_types(config['output_types'])
    })

    if run_download:
        urls_file = workspace_dir / 'input' / 'urls.txt'
        if not urls_file.exists():
            print(f"\nCould not find URLs file: {urls_file.as_posix()}")
            return
        print(f"\nDownloading to '{source_dir.relative_to(workspace_dir).as_posix()}'...")
        download_urls_to_folder(urls_file, source_dir)

    files_to_process = prompt_level_d_file_selection(workspace_dir, source_dir)
    if not files_to_process:
        return

    output_dir = workspace_dir / config['output_dir'] / selected_course
    output_dir.mkdir(parents=True, exist_ok=True)

    process_files(
        files_to_process,
        config,
        client,
        workspace_dir,
        output_dir=output_dir,
        cleanup_source_mhtml=True,
    )

    # 4. Save choices for next time
    print("\nSaving choices for next run...")
    save_config({
        'llm_provider': config['llm_provider'],
        'llm_model': config['llm_model'],
        'active_prompt': config['active_prompt'],
        'output_types': serialize_output_types(config['output_types'])
    })

    print("\n--- Wizard finished. ---")

def main():
    non_mode_args = [a for a in sys.argv[1:] if a != '-track']

    # Wizard mode: run as usual. The -track flag is accepted for backward compatibility.
    if not non_mode_args:
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
    parser.add_argument("-track", action="store_true", help="Accepted for backward compatibility; processing now outputs both inline and track-changes DOCX files.")
    parser.add_argument("--source-type", choices=['docx', 'mhtml', 'pdf', 'url'], required=True, help="The type of source to process.")
    parser.add_argument("--input", required=True, help="Path to a single input file or a URL (if --source-type is url).")
    args = parser.parse_args()

    config = load_config()
    config['llm_provider'] = normalize_provider(config.get('llm_provider', OLLAMA_PROVIDER))
    config['active_prompt'] = normalize_prompt_key(config.get('active_prompt', DEFAULT_PROMPT_KEY))
    config['output_types'] = normalize_output_types(config.get('output_types', DEFAULT_OUTPUT_TYPES))
    if config['llm_provider'] == AZURE_PROVIDER:
        azure_settings = get_azure_settings(config)
        if azure_settings['deployment_name']:
            config['llm_model'] = azure_settings['deployment_name']
    elif config['llm_provider'] == AZURE_AI_FOUNDRY_PROVIDER:
        foundry_settings = get_azure_ai_foundry_settings(config)
        if foundry_settings['model_name']:
            config['llm_model'] = foundry_settings['model_name']
    elif config['llm_provider'] == LM_STUDIO_PROVIDER:
        lm_studio_settings = get_lm_studio_settings(config)
        if lm_studio_settings['model_name']:
            config['llm_model'] = lm_studio_settings['model_name']

    workspace_dir = Path(__file__).parent

    try:
        provider = config.get('llm_provider', OLLAMA_PROVIDER)
        validate_provider_config(provider, config)
        client = create_client(provider, config)
        if provider in {OLLAMA_PROVIDER, LM_STUDIO_PROVIDER}:
            client.models.list()
    except Exception as e:
        provider = config.get('llm_provider', OLLAMA_PROVIDER)
        print(f"Error: Could not initialize {provider} client: {e}")
        if provider == AZURE_PROVIDER:
            print("Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT, and configure Azure Deployment Name.")
        elif provider == AZURE_AI_FOUNDRY_PROVIDER:
            print("Set AZURE_AI_FOUNDRY_API_KEY and AZURE_AI_FOUNDRY_ENDPOINT, and configure Azure AI Foundry Model Name.")
        elif provider == LM_STUDIO_PROVIDER:
            print("Ensure LM Studio local server is running and at least one model is loaded.")
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

    process_files(
        files_to_process,
        config,
        client,
        workspace_dir,
        source_type_for_processing,
    )

def process_files(files_to_process, config, client, workspace_dir, source_type_override=None, output_dir=None, cleanup_source_mhtml=False):
    """Loops through a list of files and processes them."""
    output_dir = output_dir or (workspace_dir / config['output_dir'])
    output_dir.mkdir(parents=True, exist_ok=True)
    mhtml_sources_to_cleanup = []
    selected_output_types = normalize_output_types(config.get('output_types', DEFAULT_OUTPUT_TYPES))

    print(f"Selected output types: {format_output_types(selected_output_types)}")

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
                if cleanup_source_mhtml:
                    mhtml_sources_to_cleanup.append(file_path)
                print(f"  -> Conversion successful. Now processing: {processing_file_path.name}")
            except Exception as e:
                print(f"  [!] MHTML to DOCX conversion failed: {e}")
                print(f"      Ensure MS Word is installed and 'win32com' is working.")
                print(f"      Skipping file: {file_path.name}")
                continue

        elif source_type == 'pdf':
            if pdf_to_docx is None:
                print("  [!] PDF to DOCX conversion is unavailable.")
                print("      This feature requires 'pywin32' (Windows only) and MS Word.")
                print("      To install, run: pip install pywin32")
                print(f"      Skipping file: {file_path.name}")
                continue

            print(f"  -> Converting PDF to DOCX using MS Word...")
            converted_docx_path = file_path.with_suffix('.from_pdf.docx')
            try:
                pdf_to_docx(str(file_path), str(converted_docx_path))
                processing_file_path = converted_docx_path
                print(f"  -> Conversion successful. Now processing: {processing_file_path.name}")
                
                # Move the original PDF to a 'pdf' subdirectory
                pdf_archive_dir = file_path.parent / 'pdf'
                try:
                    pdf_archive_dir.mkdir(exist_ok=True)
                    pdf_destination = pdf_archive_dir / file_path.name
                    file_path.rename(pdf_destination)
                    print(f"  -> Moved source PDF to: {pdf_destination.relative_to(workspace_dir).as_posix()}")
                except Exception as e:
                    print(f"  [!] Could not move PDF to archive subdirectory: {e}")
            except Exception as e:
                print(f"  [!] PDF to DOCX conversion failed: {e}")
                print(f"      Ensure MS Word is installed and 'win32com' is working.")
                print(f"      Skipping file: {file_path.name}")
                continue

        # Build corrections once, then apply them to all output styles.
        stats = {} # initialize
        try:
            correction_plan, stats = build_correction_plan(str(processing_file_path), config, client)
        except Exception as e:
            print(f"  [!] Could not build correction plan: {e}")
            print(f"      Skipping file: {file_path.name}")
            continue

        output_stem = build_output_stem(file_path)
        prompt_abbr = get_prompt_abbreviation(config.get('active_prompt', DEFAULT_PROMPT_KEY), fallback="GEN")

        for output_type in selected_output_types:
            suffix = OUTPUT_TYPE_REGISTRY[output_type]["suffix"]
            output_path = output_dir / f"{output_stem}_{prompt_abbr}_{suffix}"

            if output_type == "inline":
                try:
                    apply_inline_correction_plan(str(processing_file_path), str(output_path), correction_plan, config)
                except Exception as e:
                    print(f"  [!] Inline DOCX output failed: {e}")

            elif output_type == "uncommented":
                uncommented_config = dict(config)
                uncommented_config['add_comments'] = False
                uncommented_config['show_deletion_markers'] = False
                try:
                    apply_inline_correction_plan(str(processing_file_path), str(output_path), correction_plan, uncommented_config)
                except Exception as e:
                    print(f"  [!] Uncommented DOCX output failed: {e}")

            elif output_type == "track_changes":
                if process_docx_tracked_with_plan is None:
                    print("  [!] Tracked mode unavailable (missing tracked_processor/pywin32).")
                    print("      Skipping Track Changes output.")
                else:
                    try:
                        process_docx_tracked_with_plan(str(processing_file_path), str(output_path), correction_plan, config)
                    except Exception as e:
                        print(f"  [!] Track Changes DOCX output failed: {e}")

            elif output_type == "hybrid":
                try:
                    apply_hybrid_correction_plan(str(processing_file_path), str(output_path), correction_plan, config)
                except Exception as e:
                    print(f"  [!] Hybrid DOCX output failed: {e}")
        
        doc_end_time = time.time()
        total_doc_time = doc_end_time - doc_start_time
        
        model_used = config['llm_model']
        total_text_size = stats.get('total_text_size', 0)
        total_input_tokens = stats.get('total_input_tokens', 0)
        total_tokens_generated = stats.get('total_tokens_generated', 0)
        total_llm_time = stats.get('total_llm_time', 0)
        tokens_per_second = (total_tokens_generated / total_llm_time) if total_llm_time > 0 else 0
        
        print("\n--- Processing Summary ---")
        print(f"  Document:              {file_path.name}")
        print(f"  Total processing time: {total_doc_time:.2f} seconds")
        print(f"  Text size processed:   {total_text_size} characters")
        print(f"  Model used:            {model_used}")
        print(f"  LLM generation time:   {total_llm_time:.2f} seconds")
        print(f"  Input tokens sent:     {total_input_tokens}")
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
                'total_input_tokens': total_input_tokens,
                'total_tokens_generated': total_tokens_generated,
                'tokens_per_second': tokens_per_second
            }
            log_file = workspace_dir / config['output_dir'] / "performance_log.csv"
            log_performance_stats(log_file, log_data)
            print(f"  Performance stats logged to: {log_file.name}")
        except Exception as e:
            print(f"  [!] Could not write to performance log: {e}")
        print("--------------------------")

    if cleanup_source_mhtml:
        for source_file in mhtml_sources_to_cleanup:
            try:
                if source_file.exists() and source_file.suffix.lower() == '.mhtml':
                    source_file.unlink()
                    print(f"  -> Cleaned up source MHTML file: {source_file.name}")
            except Exception as e:
                print(f"  [!] Could not remove source MHTML file '{source_file.name}': {e}")

if __name__ == "__main__":
    main()