"""Interactive CLI wizard separated from the processing engine for easier reuse."""

from pathlib import Path

from toolkit.utils import load_config, save_config
from toolkit.output_types import OUTPUT_TYPE_REGISTRY, DEFAULT_OUTPUT_TYPES, normalize_output_types, serialize_output_types, format_output_types
from toolkit.providers import (
    OLLAMA_PROVIDER,
    LM_STUDIO_PROVIDER,
    AZURE_PROVIDER,
    AZURE_AI_FOUNDRY_PROVIDER,
    normalize_provider,
    get_azure_settings,
    get_azure_ai_foundry_settings,
    get_lm_studio_settings,
    fetch_ollama_models,
    fetch_lm_studio_models,
    format_model_label,
)
from toolkit.engine import (
    PROMPT_DEFINITIONS,
    DEFAULT_PROMPT_KEY,
    normalize_prompt_key,
    hydrate_runtime_config,
    initialize_client_for_config,
    list_processable_files,
    download_urls_to_folder,
    process_files,
    run_consistency_for_course,
)


def prompt_course_folder(workspace_dir):
    """Prompt for a course folder under input/, selecting existing or creating a new one."""
    input_root = workspace_dir / "input"
    input_root.mkdir(exist_ok=True)

    folders = sorted([directory.name for directory in input_root.iterdir() if directory.is_dir()])

    print("\n---Enter Course Number (Folder) ---")
    if folders:
        print("Existing courses and folders:")
        for index, folder_name in enumerate(folders, start=1):
            print(f"  {index}: {folder_name}")
    print("Enter a course/folder name/number (example: 1001). A new number will create new directory under 'input/'.")

    while True:
        value = input("Course folder: ").strip()
        if not value:
            print("Course number is required.")
            continue

        if value.isdigit():
            index = int(value) - 1
            if 0 <= index < len(folders):
                chosen = folders[index]
                selected_dir = input_root / chosen
                print(f"Using existing course: {chosen}")
                return chosen, selected_dir

        if any(ch in value for ch in ('/', '\\')):
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


def show_existing_files_for_course(workspace_dir, source_dir):
    """Display files already present in the selected input course folder."""
    existing_files = sorted([path for path in source_dir.iterdir() if path.is_file()])
    if not existing_files:
        return

    print("\nFiles already in selected input folder:")
    for index, file_path in enumerate(existing_files, start=1):
        print(f"  {index}: {file_path.relative_to(workspace_dir).as_posix()}")


def select_model(default_model, default_provider, config):
    """List available models and let the user select provider/model."""
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
        for index, (provider, model_name) in enumerate(options):
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
                print(f"  {index + 1}: {label} (default)")
                default_index = index
            else:
                print(f"  {index + 1}: {label}")

        default_label = default_model
        if normalized_default_provider == AZURE_PROVIDER:
            default_label = f"{default_model} (Azure OpenAI)"
        elif normalized_default_provider == AZURE_AI_FOUNDRY_PROVIDER:
            default_label = f"{default_model} (Azure AI Foundry)"
        elif normalized_default_provider == LM_STUDIO_PROVIDER:
            default_label = f"{default_model} (LM Studio)"
        elif default_model:
            default_label = f"{default_model} (Ollama)"

        selection = input(f"Select a model number to use (press Enter for default: {default_label}): ")

        if not selection.strip() and default_index != -1:
            return options[default_index]
        if not selection.strip() and options:
            print("Default model was not available. Using first listed option.")
            return options[0]

        try:
            chosen_index = int(selection) - 1
            if 0 <= chosen_index < len(options):
                return options[chosen_index]
            print("Invalid number. Using default.")
            return normalized_default_provider, default_model
        except (ValueError, IndexError):
            if selection.strip():
                print("Invalid input. Using default.")
            return normalized_default_provider, default_model
    except Exception:
        return normalize_provider(default_provider), default_model


def prompt_select_prompt_type(current_prompt_key):
    """Let the user select the prompt type shown by name and summary."""
    print("\n--- Prompt Type ---")

    options = list(PROMPT_DEFINITIONS.items())
    default_key = normalize_prompt_key(current_prompt_key)
    default_meta = PROMPT_DEFINITIONS.get(default_key, {})
    default_label = default_meta.get("name", default_key)

    for index, (prompt_key, meta) in enumerate(options, start=1):
        name = meta.get("name", prompt_key)
        summary = meta.get("summary", "")
        suffix = " (default)" if prompt_key == default_key else ""
        print(f"  {index}: {name}{suffix}")
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
    """Level A menu for selecting a high-level task."""
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
    """Prompt user for multi-select output types."""
    current = normalize_output_types(current_output_types)
    options = list(OUTPUT_TYPE_REGISTRY.items())

    print("\n--- Output Types ---")
    print("Select one or more output types by number (example: 1 3 4).")
    print("Type 'all' to select all output types. Press Enter to keep current selection.")
    print("Current selection:")
    for key in current:
        print(f"  - {OUTPUT_TYPE_REGISTRY[key]['label']} [{key}]")

    print("\nAvailable output types:")
    for index, (key, meta) in enumerate(options, start=1):
        selected_marker = "x" if key in current else " "
        print(f"  {index}: [{selected_marker}] {meta['label']} ({key})")

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
        for index in picked_indices:
            if 0 <= index < len(options):
                selected.append(options[index][0])
            else:
                print(f"Invalid selection '{index + 1}' ignored.")

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
    for index, file_path in enumerate(all_files, start=1):
        print(f"  {index}: {file_path.relative_to(workspace_dir).as_posix()}")

    print("\nEnter 'all' to process all files, or enter numbers like '1 2 3'. Press Enter to cancel.")
    selection = input("> ").strip().lower()
    if not selection:
        print("No files selected. Exiting.")
        return []
    if selection == "all":
        return all_files

    selected_files = []
    try:
        indices = [int(value) - 1 for value in selection.split()]
        for index in sorted(set(indices)):
            if 0 <= index < len(all_files):
                selected_files.append(all_files[index])
            else:
                print(f"Warning: Invalid number '{index + 1}' ignored.")
    except ValueError:
        print("Invalid input. Please enter 'all' or numbers separated by spaces.")
        return []

    return selected_files


def run_interactive_wizard():
    """Guide the user through an interactive processing session."""
    print("--- Starting Interactive Spell-Check Wizard ---")

    config = hydrate_runtime_config(load_config())
    workspace_dir = Path(__file__).resolve().parent.parent
    run_consistency_only = False

    while True:
        task_key = prompt_level_a_task()

        if task_key == "3":
            previous_provider = config["llm_provider"]
            previous_model = config["llm_model"]

            selected_provider, selected_model = select_model(
                config["llm_model"],
                config.get("llm_provider", OLLAMA_PROVIDER),
                config,
            )
            selected_provider = normalize_provider(selected_provider)

            config["llm_provider"] = selected_provider
            config["llm_model"] = selected_model
            if config["llm_provider"] == AZURE_PROVIDER:
                config["llm_model"] = get_azure_settings(config)["deployment_name"] or selected_model
            elif config["llm_provider"] == AZURE_AI_FOUNDRY_PROVIDER:
                config["llm_model"] = get_azure_ai_foundry_settings(config)["model_name"] or selected_model
            elif config["llm_provider"] == LM_STUDIO_PROVIDER:
                config["llm_model"] = selected_model
                config["lm_studio_model_name"] = selected_model

            try:
                client = initialize_client_for_config(config)
                if config["llm_provider"] in {OLLAMA_PROVIDER, LM_STUDIO_PROVIDER}:
                    client.models.list()
                save_config({
                    "llm_provider": config["llm_provider"],
                    "llm_model": config["llm_model"],
                    "lm_studio_model_name": config.get("lm_studio_model_name", ""),
                    "active_prompt": config["active_prompt"],
                })
                print(f"Saved model: {format_model_label(config['llm_model'], config['llm_provider'])}")
            except Exception as e:
                config["llm_provider"] = previous_provider
                config["llm_model"] = previous_model
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

        if task_key == "5":
            config["output_types"] = prompt_select_output_types(config.get("output_types", DEFAULT_OUTPUT_TYPES))
            save_config({"output_types": serialize_output_types(config["output_types"])})
            print(f"Saved output types: {format_output_types(config['output_types'])}")
            print("Returning to Level A menu...")
            continue

        run_consistency_only = task_key == "4"
        run_download = task_key == "2"
        break

    try:
        client = initialize_client_for_config(config)
        print(f"Using model: {format_model_label(config['llm_model'], config['llm_provider'])}")
    except Exception as e:
        provider = config["llm_provider"]
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
        print(f"\nRunning cross-document consistency analysis for '{source_dir.relative_to(workspace_dir).as_posix()}'...")
        try:
            results = run_consistency_for_course(source_dir, workspace_dir / config["output_dir"], selected_course, config, workspace_dir)
            print("\n--- Consistency Analysis Completed ---")
            print(f"Documents scanned: {results['document_count']}")
            print(f"Metadata JSON: {results['metadata_json']}")
            print(f"Documents CSV: {results['documents_csv']}")
            print(f"Keywords CSV: {results['keywords_csv']}")
            print(f"Product names CSV: {results['product_names_csv']}")
            print(f"Analysis DOCX: {results['analysis_docx']}")
            print(f"Model used: {results['model_used']} ({results['provider_used']})")
        except Exception as e:
            print(f"\nConsistency analysis failed: {e}")
        return

    print("\n--- Level C: Select Prompt Type ---")
    config["active_prompt"] = prompt_select_prompt_type(config.get("active_prompt", DEFAULT_PROMPT_KEY))
    selected_prompt = PROMPT_DEFINITIONS.get(config["active_prompt"], {})
    print(f"Using prompt: {selected_prompt.get('name', config['active_prompt'])} [{config['active_prompt']}]")
    save_config({
        "llm_provider": config["llm_provider"],
        "llm_model": config["llm_model"],
        "lm_studio_model_name": config.get("lm_studio_model_name", ""),
        "active_prompt": config["active_prompt"],
        "output_types": serialize_output_types(config["output_types"]),
    })

    if run_download:
        urls_file = workspace_dir / "input" / "urls.txt"
        if not urls_file.exists():
            print(f"\nCould not find URLs file: {urls_file.as_posix()}")
            return
        print(f"\nDownloading to '{source_dir.relative_to(workspace_dir).as_posix()}'...")
        download_urls_to_folder(urls_file, source_dir)

    files_to_process = prompt_level_d_file_selection(workspace_dir, source_dir)
    if not files_to_process:
        return

    output_dir = workspace_dir / config["output_dir"] / selected_course
    output_dir.mkdir(parents=True, exist_ok=True)

    process_files(
        files_to_process,
        config,
        client,
        workspace_dir,
        output_dir=output_dir,
        cleanup_source_mhtml=True,
    )

    print("\nSaving choices for next run...")
    save_config({
        "llm_provider": config["llm_provider"],
        "llm_model": config["llm_model"],
        "active_prompt": config["active_prompt"],
        "output_types": serialize_output_types(config["output_types"]),
    })

    print("\n--- Wizard finished. ---")
