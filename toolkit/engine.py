"""Core processing engine functions shared by CLI, future API, and other integrations."""

from collections import Counter
import concurrent.futures
import threading
from contextlib import contextmanager
import time
from datetime import datetime
from pathlib import Path

from toolkit.utils import format_path_for_display, get_input_root, log_performance_stats
from toolkit.document_processor import build_correction_plan, apply_inline_correction_plan, apply_hybrid_correction_plan, build_prepend_plan, apply_prepend_plan, build_course_summary_plan, save_course_summary
from toolkit.web_tools import download_url_as_mhtml
from toolkit.output_types import OUTPUT_TYPE_REGISTRY, DEFAULT_OUTPUT_TYPES, normalize_output_types, format_output_types
from toolkit.summary_report import summarize_correction_plan, update_summary_report
from toolkit.providers import (
    OLLAMA_PROVIDER,
    LM_STUDIO_PROVIDER,
    AZURE_AI_FOUNDRY_PROVIDER,
    normalize_provider,
    get_azure_ai_foundry_settings,
    get_lm_studio_settings,
    validate_provider_config,
    create_client,
)

from toolkit.prompts import PROMPT_DEFINITIONS, DEFAULT_PROMPT_KEY, get_prompt_abbreviation, get_prompt_output_mode


_PARALLEL_FILE_WORKER_LOCK = threading.Lock()
_ACTIVE_PARALLEL_FILE_WORKERS = 0
_PEAK_PARALLEL_FILE_WORKERS = 0


@contextmanager
def _track_parallel_file_worker():
    global _ACTIVE_PARALLEL_FILE_WORKERS, _PEAK_PARALLEL_FILE_WORKERS
    with _PARALLEL_FILE_WORKER_LOCK:
        _ACTIVE_PARALLEL_FILE_WORKERS += 1
        _PEAK_PARALLEL_FILE_WORKERS = max(_PEAK_PARALLEL_FILE_WORKERS, _ACTIVE_PARALLEL_FILE_WORKERS)
    try:
        yield
    finally:
        with _PARALLEL_FILE_WORKER_LOCK:
            _ACTIVE_PARALLEL_FILE_WORKERS = max(0, _ACTIVE_PARALLEL_FILE_WORKERS - 1)


def get_parallel_file_runtime_telemetry() -> dict:
    """Return runtime telemetry for file-level worker activity."""
    with _PARALLEL_FILE_WORKER_LOCK:
        return {
            "activeParallelFileWorkers": int(_ACTIVE_PARALLEL_FILE_WORKERS),
            "peakParallelFileWorkers": int(_PEAK_PARALLEL_FILE_WORKERS),
        }

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
    try:
        runtime_config["llm_max_parallel_files"] = max(1, min(8, int(runtime_config.get("llm_max_parallel_files", 1))))
    except (TypeError, ValueError):
        runtime_config["llm_max_parallel_files"] = 1

    # Preserve saved llm_model from config; only use provider settings as fallback if model is not saved
    saved_model = str(runtime_config.get("llm_model", "")).strip()
    
    if runtime_config["llm_provider"] == AZURE_AI_FOUNDRY_PROVIDER:
        if not saved_model:
            foundry_settings = get_azure_ai_foundry_settings(runtime_config)
            if foundry_settings["selected_value"]:
                runtime_config["llm_model"] = foundry_settings["selected_value"]
    elif runtime_config["llm_provider"] == LM_STUDIO_PROVIDER:
        if not saved_model:
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


def _render_output_type(output_type, processing_file_path, output_path, correction_plan, config):
    """Render one output type for a precomputed correction plan."""
    processing_path = str(processing_file_path)
    destination_path = str(output_path)

    if output_type == "inline":
        apply_inline_correction_plan(processing_path, destination_path, correction_plan, config)
        return

    if output_type == "uncommented":
        uncommented_config = dict(config)
        uncommented_config["add_comments"] = False
        uncommented_config["show_deletion_markers"] = False
        apply_inline_correction_plan(processing_path, destination_path, correction_plan, uncommented_config)
        return

    if output_type == "track_changes":
        if process_docx_tracked_with_plan is None:
            raise RuntimeError("Tracked mode unavailable (missing tracked_processor/pywin32).")
        process_docx_tracked_with_plan(processing_path, destination_path, correction_plan, config)
        return

    if output_type == "hybrid":
        apply_hybrid_correction_plan(processing_path, destination_path, correction_plan, config)
        return

    raise ValueError(f"Unsupported output type: {output_type}")


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
        mhtml_output_dir = get_input_root()
        mhtml_output_dir.mkdir(exist_ok=True, parents=True)
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
        "metadata_json": format_path_for_display(Path(results["metadata_json"]), workspace_dir),
        "documents_csv": format_path_for_display(Path(results["documents_csv"]), workspace_dir),
        "keywords_csv": format_path_for_display(Path(results["keywords_csv"]), workspace_dir),
        "product_names_csv": format_path_for_display(Path(results["product_names_csv"]), workspace_dir),
        "analysis_docx": format_path_for_display(Path(results["analysis_docx"]), workspace_dir),
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

    output_dir = Path(output_dir) if output_dir is not None else Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    mhtml_sources_to_cleanup = []
    selected_output_types = normalize_output_types(config.get("output_types", DEFAULT_OUTPUT_TYPES))
    run_timestamp = datetime.now().isoformat()
    run_status = "completed"
    run_files = []
    run_category_counts = Counter()
    run_totals = {
        "correctionCount": 0,
        "totalInputTokens": 0,
        "totalTokensGenerated": 0,
        "totalLlmTime": 0.0,
    }
    canceled_error = None

    print(f"Selected output types: {format_output_types(selected_output_types)}")

    # Check if this is a course-level summary request (handles all files at once, not per-file)
    active_prompt_key = config.get("active_prompt", DEFAULT_PROMPT_KEY)
    output_mode = get_prompt_output_mode(active_prompt_key)
    
    if output_mode == "course_summary":
        print("\n--- Running Course Summary Analysis (Folder-Level) ---")
        try:
            # Convert all file paths to .docx format first (if needed)
            docx_files = []
            for file_path in files_to_process:
                _raise_if_canceled()
                if file_path.suffix.lower() == ".docx":
                    docx_files.append(file_path)
            
            if not docx_files:
                print("  [!] No valid documents found for course summary analysis.")
                return {
                    "files": [],
                    "timestamp": run_timestamp,
                    "status": "failed",
                    "error": "No documents provided",
                }
            
            print(f"Building course summary from {len(docx_files)} document(s)...")
            course_summary_text, stats = build_course_summary_plan(docx_files, config, client)
            
            if course_summary_text:
                # Save course summary as standalone file in the output directory
                summary_output_path = output_dir / "Course_Summary.docx"
                save_course_summary(str(summary_output_path), course_summary_text)
                
                run_totals["totalInputTokens"] = stats["total_input_tokens"]
                run_totals["totalTokensGenerated"] = stats["total_tokens_generated"]
                run_totals["totalLlmTime"] = stats["total_llm_time"]
                
                run_files.append({
                    "file": "Course_Summary.docx",
                    "location": format_path_for_display(summary_output_path, workspace_dir),
                    "inputTokens": stats["total_input_tokens"],
                    "tokensGenerated": stats["total_tokens_generated"],
                    "llmTime": stats["total_llm_time"],
                })
                print(f"Course summary completed in {stats['total_llm_time']:.2f}s")
            else:
                print("  [!] Course summary generation returned empty text.")
                run_status = "failed"
        except Exception as e:
            print(f"  [!] Error during course summary generation: {e}")
            run_status = "failed"
            canceled_error = e
        
        # Return early for course summary (no per-document performance stats to log)
        return {
            "files": run_files,
            "timestamp": run_timestamp,
            "status": run_status,
            "summary": {"correctionCount": 0, "categoryCount": {}},
        }

    try:
        max_parallel_files = max(1, min(8, int(config.get("llm_max_parallel_files", 1) or 1)))
        worker_local = threading.local()

        def _worker_client():
            if max_parallel_files <= 1:
                return client
            local_client = getattr(worker_local, "client", None)
            if local_client is None:
                local_client = initialize_client_for_config(config)
                worker_local.client = local_client
            return local_client

        def _process_single_file(index, file_path):
            with _track_parallel_file_worker():
                _raise_if_canceled()
                print(f"\n--- Processing: {file_path.name} ---")
                doc_start_time = time.time()

                processing_file_path = file_path
                source_type = source_type_override or file_path.suffix.lower().strip(".")
                mhtml_cleanup_source = None

                if source_type == "mhtml":
                    if mhtml_to_docx is None:
                        print("  [!] MHTML to DOCX conversion is unavailable.")
                        print("      This feature requires 'pywin32' (Windows only) and MS Word.")
                        print("      To install, run: pip install pywin32")
                        print(f"      Skipping file: {file_path.name}")
                        return None

                    print("  -> Converting MHTML to DOCX using MS Word...")
                    converted_docx_path = file_path.with_suffix(".docx")
                    try:
                        mhtml_to_docx(str(file_path), str(converted_docx_path))
                        processing_file_path = converted_docx_path
                        if cleanup_source_mhtml:
                            mhtml_cleanup_source = file_path
                        print(f"  -> Conversion successful. Now processing: {processing_file_path.name}")
                    except Exception as e:
                        print(f"  [!] MHTML to DOCX conversion failed: {e}")
                        print("      Ensure MS Word is installed and 'win32com' is working.")
                        print(f"      Skipping file: {file_path.name}")
                        return None

                elif source_type == "pdf":
                    if pdf_to_docx is None:
                        print("  [!] PDF to DOCX conversion is unavailable.")
                        print("      This feature requires 'pywin32' (Windows only) and MS Word.")
                        print("      To install, run: pip install pywin32")
                        print(f"      Skipping file: {file_path.name}")
                        return None
                    try:
                        print("  -> Converting PDF to DOCX using MS Word...")
                        converted_docx_path = file_path.with_suffix(".from_pdf.docx")
                        pdf_to_docx(str(file_path), str(converted_docx_path))
                        processing_file_path = converted_docx_path
                        print(f"  -> Conversion successful. Now processing: {processing_file_path.name}")

                        try:
                            pdf_archive_dir = file_path.parent / "pdf"
                            pdf_archive_dir.mkdir(exist_ok=True)
                            pdf_destination = pdf_archive_dir / file_path.name
                            file_path.rename(pdf_destination)
                            print(f"  -> Moved source PDF to: {format_path_for_display(pdf_destination, workspace_dir)}")
                        except Exception as e:
                            print(f"  [!] Could not move PDF to archive subdirectory: {e}")
                    except Exception as e:
                        print(f"  [!] PDF to DOCX conversion failed: {e}")
                        print("      Ensure MS Word is installed and 'win32com' is working.")
                        print(f"      Skipping file: {file_path.name}")
                        return None

                try:
                    active_prompt_key = config.get("active_prompt", DEFAULT_PROMPT_KEY)
                    output_mode = get_prompt_output_mode(active_prompt_key)
                    prompt_abbr = get_prompt_abbreviation(active_prompt_key, fallback="GEN")
                    output_stem = build_output_stem(file_path)
                    processing_client = _worker_client()

                    if output_mode == "prepend_text":
                        prepend_text, stats = build_prepend_plan(
                            str(processing_file_path),
                            config,
                            processing_client,
                        )
                        if prepend_text:
                            output_path = output_dir / f"{output_stem}_{prompt_abbr}.docx"
                            apply_prepend_plan(str(processing_file_path), str(output_path), prepend_text)
                            successful_output_types = ["prepend_text"]
                        else:
                            print("  [!] Summary generation returned empty text. Skipping output.")
                            successful_output_types = []
                        correction_summary = {"correctionCount": 0, "categoryCounts": {}}
                    else:
                        correction_plan, stats = build_correction_plan(
                            str(processing_file_path),
                            config,
                            processing_client,
                            should_cancel=_raise_if_canceled,
                        )
                        correction_summary = summarize_correction_plan(correction_plan)
                        successful_output_types = []

                        for output_type in selected_output_types:
                            suffix = OUTPUT_TYPE_REGISTRY[output_type]["suffix"]
                            output_path = output_dir / f"{output_stem}_{prompt_abbr}_{suffix}"
                            try:
                                _raise_if_canceled()
                                _render_output_type(
                                    output_type,
                                    processing_file_path,
                                    output_path,
                                    correction_plan,
                                    config,
                                )
                                successful_output_types.append(output_type)
                            except RuntimeError as e:
                                if output_type == "track_changes":
                                    print(f"  [!] {e}")
                                    print("      Skipping Track Changes output.")
                                else:
                                    print(f"  [!] {output_type} DOCX output failed: {e}")
                            except Exception as e:
                                print(f"  [!] {output_type} DOCX output failed: {e}")

                except Exception as e:
                    if str(e) == "Canceled by user request":
                        raise
                    print(f"  [!] Could not process file: {e}")
                    print(f"      Skipping file: {file_path.name}")
                    return None

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
                print(f"  Corrections captured:  {correction_summary['correctionCount']}")

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
                    log_file = output_dir / "performance_log.csv"
                    log_performance_stats(log_file, log_data)
                    print(f"  Performance stats logged to: {log_file.name}")
                except Exception as e:
                    print(f"  [!] Could not write to performance log: {e}")
                print("--------------------------")

                return {
                    "index": index,
                    "cleanup_source": mhtml_cleanup_source,
                    "categoryCounts": correction_summary.get("categoryCounts", {}),
                    "correctionCount": int(correction_summary.get("correctionCount", 0)),
                    "totalInputTokens": int(total_input_tokens),
                    "totalTokensGenerated": int(total_tokens_generated),
                    "totalLlmTime": float(total_llm_time),
                    "fileEntry": {
                        "name": file_path.name,
                        "sourceType": source_type,
                        "correctionCount": int(correction_summary.get("correctionCount", 0)),
                        "categoryCounts": correction_summary.get("categoryCounts", {}),
                        "totalDocTime": total_doc_time,
                        "totalTextSize": int(total_text_size),
                        "totalInputTokens": int(total_input_tokens),
                        "totalTokensGenerated": int(total_tokens_generated),
                        "totalLlmTime": float(total_llm_time),
                        "outputTypesGenerated": successful_output_types,
                    },
                }

        file_results = []
        if max_parallel_files > 1 and len(files_to_process) > 1:
            print(f"\n--- Parallel file processing enabled ({max_parallel_files} workers) ---")
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel_files) as executor:
                future_map = {
                    executor.submit(_process_single_file, index, file_path): (index, file_path)
                    for index, file_path in enumerate(files_to_process)
                }
                for future in concurrent.futures.as_completed(future_map):
                    _raise_if_canceled()
                    try:
                        result = future.result()
                        if result is not None:
                            file_results.append(result)
                    except Exception:
                        for pending in future_map:
                            pending.cancel()
                        raise
        else:
            for index, file_path in enumerate(files_to_process):
                result = _process_single_file(index, file_path)
                if result is not None:
                    file_results.append(result)

        file_results.sort(key=lambda item: item.get("index", 0))
        for result in file_results:
            cleanup_source = result.get("cleanup_source")
            if cleanup_source is not None:
                mhtml_sources_to_cleanup.append(cleanup_source)

            run_totals["correctionCount"] += int(result.get("correctionCount", 0))
            run_totals["totalInputTokens"] += int(result.get("totalInputTokens", 0))
            run_totals["totalTokensGenerated"] += int(result.get("totalTokensGenerated", 0))
            run_totals["totalLlmTime"] += float(result.get("totalLlmTime", 0.0))

            for category, count in (result.get("categoryCounts") or {}).items():
                run_category_counts[category] += int(count or 0)

            file_entry = result.get("fileEntry")
            if file_entry:
                run_files.append(file_entry)
    except Exception as e:
        if str(e) == "Canceled by user request":
            run_status = "canceled"
            canceled_error = e
        else:
            run_status = "failed"
            raise
    finally:
        run_record = {
            "runId": run_timestamp,
            "timestamp": run_timestamp,
            "status": run_status,
            "provider": config.get("llm_provider", ""),
            "model": config.get("llm_model", ""),
            "promptKey": config.get("active_prompt", DEFAULT_PROMPT_KEY),
            "outputTypes": selected_output_types,
            "fileCount": len(run_files),
            "correctionCount": int(run_totals["correctionCount"]),
            "categoryCounts": dict(run_category_counts),
            "totalInputTokens": int(run_totals["totalInputTokens"]),
            "totalTokensGenerated": int(run_totals["totalTokensGenerated"]),
            "totalLlmTime": float(run_totals["totalLlmTime"]),
            "files": run_files,
        }
        try:
            summary_artifacts = update_summary_report(output_dir, run_record)
            print(f"Summary report updated: {summary_artifacts['reportPath'].name}")
        except Exception as e:
            print(f"  [!] Could not update summary report: {e}")

        if cleanup_source_mhtml:
            for source_file in mhtml_sources_to_cleanup:
                try:
                    if source_file.exists() and source_file.suffix.lower() == ".mhtml":
                        source_file.unlink()
                        print(f"  -> Cleaned up source MHTML file: {source_file.name}")
                except Exception as e:
                    print(f"  [!] Could not remove source MHTML file '{source_file.name}': {e}")

    if canceled_error is not None:
        raise canceled_error

    return run_record
