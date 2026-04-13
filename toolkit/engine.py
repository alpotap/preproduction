"""Core processing engine functions shared by CLI, future API, and other integrations."""

import time
from datetime import datetime
from pathlib import Path

from toolkit.utils import log_performance_stats
from toolkit.document_processor import build_correction_plan, apply_inline_correction_plan, apply_hybrid_correction_plan
from toolkit.web_tools import download_url_as_mhtml
from toolkit.output_types import OUTPUT_TYPE_REGISTRY, DEFAULT_OUTPUT_TYPES, normalize_output_types, format_output_types
from toolkit.providers import (
    OLLAMA_PROVIDER,
    LM_STUDIO_PROVIDER,
    AZURE_PROVIDER,
    AZURE_AI_FOUNDRY_PROVIDER,
    normalize_provider,
    get_azure_settings,
    get_azure_ai_foundry_settings,
    get_lm_studio_settings,
    validate_provider_config,
    create_client,
)

try:
    from toolkit.prompts import PROMPT_DEFINITIONS, DEFAULT_PROMPT_KEY, get_prompt_abbreviation
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
    from toolkit.tracked_processor import process_docx_tracked_with_plan
except (ImportError, ModuleNotFoundError):
    process_docx_tracked_with_plan = None

try:
    from toolkit.convert import mhtml_to_docx, pdf_to_docx
except (ImportError, ModuleNotFoundError):
    mhtml_to_docx = None
    pdf_to_docx = None

try:
    from toolkit.consistency_full_tool import run_full_consistency
except (ImportError, ModuleNotFoundError):
    run_full_consistency = None


def normalize_prompt_key(prompt_key):
    """Return a valid prompt key, falling back to the default prompt."""
    if prompt_key in PROMPT_DEFINITIONS:
        return prompt_key
    return DEFAULT_PROMPT_KEY if DEFAULT_PROMPT_KEY in PROMPT_DEFINITIONS else next(iter(PROMPT_DEFINITIONS.keys()))


def hydrate_runtime_config(config):
    """Normalize persisted config and fill runtime-derived model values."""
    runtime_config = dict(config)
    runtime_config["llm_provider"] = normalize_provider(runtime_config.get("llm_provider", OLLAMA_PROVIDER))
    runtime_config["active_prompt"] = normalize_prompt_key(runtime_config.get("active_prompt", DEFAULT_PROMPT_KEY))
    runtime_config["output_types"] = normalize_output_types(runtime_config.get("output_types", DEFAULT_OUTPUT_TYPES))

    if runtime_config["llm_provider"] == AZURE_PROVIDER:
        azure_settings = get_azure_settings(runtime_config)
        if azure_settings["deployment_name"]:
            runtime_config["llm_model"] = azure_settings["deployment_name"]
    elif runtime_config["llm_provider"] == AZURE_AI_FOUNDRY_PROVIDER:
        foundry_settings = get_azure_ai_foundry_settings(runtime_config)
        if foundry_settings["model_name"]:
            runtime_config["llm_model"] = foundry_settings["model_name"]
    elif runtime_config["llm_provider"] == LM_STUDIO_PROVIDER:
        lm_studio_settings = get_lm_studio_settings(runtime_config)
        if lm_studio_settings["model_name"]:
            runtime_config["llm_model"] = lm_studio_settings["model_name"]

    return runtime_config


def initialize_client_for_config(config):
    """Validate provider settings and create a ready-to-use client."""
    provider = config.get("llm_provider", OLLAMA_PROVIDER)
    validate_provider_config(provider, config)
    client = create_client(provider, config)
    if provider in {OLLAMA_PROVIDER, LM_STUDIO_PROVIDER}:
        client.models.list()
    return client


def list_processable_files(source_dir):
    """Return sorted processable files from a source folder."""
    return sorted(
        [f for f in source_dir.glob("*.docx") if "_corrected" not in f.name]
        + [f for f in source_dir.glob("*.mhtml") if "_corrected" not in f.name]
        + [f for f in source_dir.glob("*.pdf")]
    )


def build_output_stem(file_path):
    """Return a stable output stem without conversion-source suffixes."""
    stem = file_path.stem
    for suffix in (".from_mhtml", ".from_pdf"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem


def download_urls_to_folder(urls_file, mhtml_output_dir):
    """Download URLs from urls.txt into a selected course folder."""
    with open(urls_file, "r", encoding="utf-8") as file_handle:
        urls = [line.strip() for line in file_handle if line.strip() and not line.startswith("#")]

    print(f"Found {len(urls)} URL(s) to process.")
    downloaded_files = []
    for url in urls:
        downloaded = download_url_as_mhtml(url, mhtml_output_dir)
        if downloaded:
            downloaded_files.append(downloaded)
    return downloaded_files


def resolve_input_sources(input_value, source_type, workspace_dir):
    """Resolve a CLI/API input into processable file paths and effective source type."""
    files_to_process = []
    source_type_for_processing = source_type

    if source_type == "url":
        mhtml_output_dir = workspace_dir / "input"
        mhtml_output_dir.mkdir(exist_ok=True)
        downloaded_file = download_url_as_mhtml(input_value, mhtml_output_dir)
        if downloaded_file:
            files_to_process.append(downloaded_file)
            source_type_for_processing = "mhtml"
    else:
        input_path = Path(input_value)
        if not input_path.is_file():
            raise FileNotFoundError(f"Input file not found at '{input_path}'")
        files_to_process.append(input_path)

    return files_to_process, source_type_for_processing


def run_consistency_for_course(source_dir, output_dir, selected_course, config, workspace_dir):
    """Run consistency analysis for one selected course folder."""
    if run_full_consistency is None:
        raise RuntimeError("Consistency tools are unavailable. Ensure consistency_full_tool.py is present.")

    consistency_output_dir = output_dir / selected_course / "consistency"
    consistency_docx = consistency_output_dir / "consistency_analysis.docx"
    results = run_full_consistency(source_dir, consistency_output_dir, consistency_docx)
    return {
        "document_count": results["document_count"],
        "metadata_json": Path(results["metadata_json"]).relative_to(workspace_dir).as_posix(),
        "documents_csv": Path(results["documents_csv"]).relative_to(workspace_dir).as_posix(),
        "keywords_csv": Path(results["keywords_csv"]).relative_to(workspace_dir).as_posix(),
        "product_names_csv": Path(results["product_names_csv"]).relative_to(workspace_dir).as_posix(),
        "analysis_docx": Path(results["analysis_docx"]).relative_to(workspace_dir).as_posix(),
        "model_used": results["model_used"],
        "provider_used": results["provider_used"],
    }


def process_files(
    files_to_process,
    config,
    client,
    workspace_dir,
    source_type_override=None,
    output_dir=None,
    cleanup_source_mhtml=False,
    should_cancel=None,
):
    """Process a list of source files using the shared correction-plan pipeline."""
    def _raise_if_canceled():
        if callable(should_cancel) and should_cancel():
            raise RuntimeError("Canceled by user request")

    output_dir = output_dir or (workspace_dir / config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    mhtml_sources_to_cleanup = []
    selected_output_types = normalize_output_types(config.get("output_types", DEFAULT_OUTPUT_TYPES))

    print(f"Selected output types: {format_output_types(selected_output_types)}")

    for file_path in files_to_process:
        _raise_if_canceled()
        print(f"\n--- Processing: {file_path.name} ---")
        doc_start_time = time.time()

        processing_file_path = file_path
        source_type = source_type_override or file_path.suffix.lower().strip(".")

        if source_type == "mhtml":
            if mhtml_to_docx is None:
                print("  [!] MHTML to DOCX conversion is unavailable.")
                print("      This feature requires 'pywin32' (Windows only) and MS Word.")
                print("      To install, run: pip install pywin32")
                print(f"      Skipping file: {file_path.name}")
                continue

            print("  -> Converting MHTML to DOCX using MS Word...")
            converted_docx_path = file_path.with_suffix(".from_mhtml.docx")
            try:
                mhtml_to_docx(str(file_path), str(converted_docx_path))
                processing_file_path = converted_docx_path
                if cleanup_source_mhtml:
                    mhtml_sources_to_cleanup.append(file_path)
                print(f"  -> Conversion successful. Now processing: {processing_file_path.name}")
            except Exception as e:
                print(f"  [!] MHTML to DOCX conversion failed: {e}")
                print("      Ensure MS Word is installed and 'win32com' is working.")
                print(f"      Skipping file: {file_path.name}")
                continue

        elif source_type == "pdf":
            if pdf_to_docx is None:
                print("  [!] PDF to DOCX conversion is unavailable.")
                print("      This feature requires 'pywin32' (Windows only) and MS Word.")
                print("      To install, run: pip install pywin32")
                print(f"      Skipping file: {file_path.name}")
                continue

            print("  -> Converting PDF to DOCX using MS Word...")
            converted_docx_path = file_path.with_suffix(".from_pdf.docx")
            try:
                pdf_to_docx(str(file_path), str(converted_docx_path))
                processing_file_path = converted_docx_path
                print(f"  -> Conversion successful. Now processing: {processing_file_path.name}")

                pdf_archive_dir = file_path.parent / "pdf"
                try:
                    pdf_archive_dir.mkdir(exist_ok=True)
                    pdf_destination = pdf_archive_dir / file_path.name
                    file_path.rename(pdf_destination)
                    print(f"  -> Moved source PDF to: {pdf_destination.relative_to(workspace_dir).as_posix()}")
                except Exception as e:
                    print(f"  [!] Could not move PDF to archive subdirectory: {e}")
            except Exception as e:
                print(f"  [!] PDF to DOCX conversion failed: {e}")
                print("      Ensure MS Word is installed and 'win32com' is working.")
                print(f"      Skipping file: {file_path.name}")
                continue

        try:
            correction_plan, stats = build_correction_plan(
                str(processing_file_path),
                config,
                client,
                should_cancel=_raise_if_canceled,
            )
        except Exception as e:
            if str(e) == "Canceled by user request":
                raise
            print(f"  [!] Could not build correction plan: {e}")
            print(f"      Skipping file: {file_path.name}")
            continue

        output_stem = build_output_stem(file_path)
        prompt_abbr = get_prompt_abbreviation(config.get("active_prompt", DEFAULT_PROMPT_KEY), fallback="GEN")

        for output_type in selected_output_types:
            _raise_if_canceled()
            suffix = OUTPUT_TYPE_REGISTRY[output_type]["suffix"]
            output_path = output_dir / f"{output_stem}_{prompt_abbr}_{suffix}"

            if output_type == "inline":
                try:
                    apply_inline_correction_plan(str(processing_file_path), str(output_path), correction_plan, config)
                except Exception as e:
                    print(f"  [!] Inline DOCX output failed: {e}")

            elif output_type == "uncommented":
                uncommented_config = dict(config)
                uncommented_config["add_comments"] = False
                uncommented_config["show_deletion_markers"] = False
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

        total_doc_time = time.time() - doc_start_time
        model_used = config["llm_model"]
        total_text_size = stats.get("total_text_size", 0)
        total_input_tokens = stats.get("total_input_tokens", 0)
        total_tokens_generated = stats.get("total_tokens_generated", 0)
        total_llm_time = stats.get("total_llm_time", 0)
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

        try:
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "document_name": file_path.name,
                "model_used": model_used,
                "total_doc_time": total_doc_time,
                "total_text_size": total_text_size,
                "total_llm_time": total_llm_time,
                "total_input_tokens": total_input_tokens,
                "total_tokens_generated": total_tokens_generated,
                "tokens_per_second": tokens_per_second,
            }
            log_file = workspace_dir / config["output_dir"] / "performance_log.csv"
            log_performance_stats(log_file, log_data)
            print(f"  Performance stats logged to: {log_file.name}")
        except Exception as e:
            print(f"  [!] Could not write to performance log: {e}")
        print("--------------------------")

    if cleanup_source_mhtml:
        for source_file in mhtml_sources_to_cleanup:
            try:
                if source_file.exists() and source_file.suffix.lower() == ".mhtml":
                    source_file.unlink()
                    print(f"  -> Cleaned up source MHTML file: {source_file.name}")
            except Exception as e:
                print(f"  [!] Could not remove source MHTML file '{source_file.name}': {e}")
