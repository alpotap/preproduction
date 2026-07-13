"""Local FastAPI server hosting a single-page UI for the document processing tool."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Literal
from urllib.parse import quote
import threading
import zipfile

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from toolkit.utils import load_config, save_config
from toolkit.engine import hydrate_runtime_config
from toolkit.prompts import get_selectable_prompt_definitions
from toolkit.output_types import OUTPUT_TYPE_REGISTRY, normalize_output_types, serialize_output_types
from toolkit.providers import (
    OLLAMA_PROVIDER,
    LM_STUDIO_PROVIDER,
    AZURE_AI_FOUNDRY_PROVIDER,
    fetch_ollama_models,
    fetch_lm_studio_models,
    get_lm_studio_settings,
    get_azure_ai_foundry_settings,
)
from toolkit.runtime_yaml import (
    ensure_runtime_yaml_exists,
    load_runtime_yaml,
    get_yaml_providers_and_models,
    apply_runtime_yaml_overrides,
)
from toolkit.web_jobs import (
    EXECUTION_LOG_PATH,
    INPUT_DIR,
    OUTPUT_DIR,
    RAW_OUTPUT_LOG_PATH,
    PERFORMANCE_LOG_PATH,
    WORKSPACE_DIR,
    job_manager,
    tail_text_file,
)
from toolkit.debug_collector import DebugCollector

APP_TITLE = "Document Correction Toolkit"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
STATIC_DIR = WORKSPACE_DIR / "webapp" / "static"
HIDDEN_OUTPUT_FILENAMES = {"summary_report_state.json"}
HIDDEN_OUTPUT_DIRNAMES = {".ai_cache"}
RENDER_CACHE_PREFIX = "cache"

app = FastAPI(title=APP_TITLE)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
ensure_runtime_yaml_exists()

# Debug collector for remote diagnostics
debug_collector = DebugCollector(OUTPUT_DIR)


class CreateFolderRequest(BaseModel):
    name: str


class EnqueueJobRequest(BaseModel):
    taskType: Literal["process", "download_process", "render_cached", "consistency"]
    folder: str
    promptKey: str | None = None
    outputTypes: list[str] | None = None
    notifyTerminalPunctuation: bool | None = None
    urls: str | None = None
    selectedFiles: list[str] | None = None


class SavePreferencesRequest(BaseModel):
    promptKey: str | None = None
    outputTypes: list[str] | None = None
    notifyTerminalPunctuation: bool | None = None


def _build_config_updates(
    prompt_key: str | None,
    output_types: list[str] | None,
    notify_terminal_punctuation: bool | None,
) -> dict[str, str]:
    updates: dict[str, str] = {}

    if output_types is not None:
        updates["output_types"] = serialize_output_types(normalize_output_types(output_types))

    if prompt_key:
        updates["active_prompt"] = prompt_key

    if notify_terminal_punctuation is not None:
        updates["notify_terminal_punctuation"] = "true" if notify_terminal_punctuation else "false"

    return updates


def _build_prompt_details(prompt_definition: dict) -> str:
    details: list[str] = []
    version = str(prompt_definition.get("version", "")).strip()
    if version:
        details.append(f"Version {version}")

    if prompt_definition.get("prompt_category") == "staging":
        source_key = str(prompt_definition.get("source_prompt_key", "")).strip()
        if source_key:
            details.append(f"Staging source: {source_key}")

    summary = str(prompt_definition.get("summary", "")).strip()
    if summary:
        details.append(summary)

    template = str(prompt_definition.get("template", ""))
    focus_items: list[str] = []
    for raw_line in template.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "{text}" in line or "{language}" in line:
            continue
        if line.startswith("Strict Constraints") or line.startswith("Output ONLY") or line.startswith("Example:"):
            continue
        if line.startswith("•"):
            focus_items.append(line.lstrip("• ").rstrip("."))
    if focus_items:
        details.append("Focus: " + "; ".join(focus_items[:3]))

    max_input_words = prompt_definition.get("max_input_words")
    if max_input_words:
        details.append(f"Chunk size up to {max_input_words} words")

    return " ".join(details).strip()


@app.get("/")
def serve_index() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/capabilities")
def get_capabilities() -> dict:
    runtime_yaml = load_runtime_yaml()
    config = apply_runtime_yaml_overrides(hydrate_runtime_config(load_config()), runtime_yaml)
    providers, _provider_models = get_yaml_providers_and_models(runtime_yaml)
    selectable_prompts = get_selectable_prompt_definitions()

    return {
        "config": {
            "llmProvider": str(config.get("llm_provider", "")).strip(),
            "llmModel": str(config.get("llm_model", "")).strip(),
            "activePrompt": config.get("active_prompt"),
            "outputTypes": config.get("output_types"),
            "llmMaxPasses": config.get("llm_max_passes"),
            "llmMaxConcurrentRequests": config.get("llm_max_concurrent_requests"),
            "llmMaxParallelFiles": config.get("llm_max_parallel_files"),
            "configYamlPath": "config.yaml",
            "configYamlVersion": runtime_yaml.get("version", 1),
            "notifyTerminalPunctuation": bool(config.get("notify_terminal_punctuation", True)),
        },
        "prompts": [
            {
                "key": key,
                "abbr": value.get("abbr", ""),
                "name": value.get("name", key),
                "version": value.get("version", "1.0"),
                "summary": value.get("summary", ""),
                "details": _build_prompt_details(value),
                "category": value.get("prompt_category", "copy_editing"),
            }
            for key, value in selectable_prompts.items()
        ],
        "promptCategories": [
            {"key": "copy_editing", "label": "Copy Editing"},
            {"key": "document_analysis", "label": "Document Analysis"},
            {"key": "multi_document_analysis", "label": "Multi-Document Analysis"},
            {"key": "staging", "label": "Staging"},
        ],
        "outputTypes": [
            {
                "key": key,
                "label": meta["label"],
                "suffix": meta["suffix"],
            }
            for key, meta in OUTPUT_TYPE_REGISTRY.items()
        ],
        "providers": providers,
    }


@app.get("/api/models")
def get_models(provider: str = Query(...)) -> dict:
    runtime_yaml = load_runtime_yaml()
    _providers, provider_models = get_yaml_providers_and_models(runtime_yaml)
    provider = provider.strip().lower()
    if provider not in {OLLAMA_PROVIDER, LM_STUDIO_PROVIDER, AZURE_AI_FOUNDRY_PROVIDER}:
        raise HTTPException(status_code=400, detail="Unsupported provider")
    models = provider_models.get(provider, [])
    return {"models": models}


@app.get("/api/folders")
def list_folders(scope: Literal["input", "output"] = Query("input")) -> dict:
    root = _resolve_scope_root(scope)
    root.mkdir(parents=True, exist_ok=True)
    folders = sorted([path.name for path in root.iterdir() if path.is_dir()])
    return {"folders": folders}


@app.post("/api/folders")
def create_folder(payload: CreateFolderRequest) -> dict:
    folder = _validate_folder_name(payload.name)
    target_dir = INPUT_DIR / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    return {"folder": folder}


@app.post("/api/uploads")
async def upload_files(folder: str = Query(...), files: list[UploadFile] = File(...)) -> dict:
    folder_name = _validate_folder_name(folder)
    target_dir = INPUT_DIR / folder_name
    target_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    rejected = []
    extraction_started = []
    for upload in files:
        filename = Path(upload.filename or "").name
        if not filename:
            rejected.append({"name": upload.filename or "", "reason": "Missing filename"})
            continue

        data = await upload.read()
        if len(data) > MAX_UPLOAD_BYTES:
            rejected.append({"name": filename, "reason": "File exceeds 20 MB limit"})
            continue

        destination = target_dir / filename
        with open(destination, "wb") as file_handle:
            file_handle.write(data)

        is_zip = destination.suffix.lower() == ".zip"
        saved.append({"name": filename, "size": len(data), "isZip": is_zip})
        if is_zip:
            extraction_started.append(filename)
            worker = threading.Thread(
                target=_extract_zip_background,
                args=(destination, target_dir),
                daemon=True,
                name=f"zip-extract-{destination.stem}",
            )
            worker.start()

    return {"saved": saved, "rejected": rejected, "extractionStarted": extraction_started}


@app.get("/api/files")
def list_files(
    scope: Literal["input", "output"] = Query("input"),
    folder: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
) -> dict:
    base_dir = _resolve_scope_root(scope)
    target_dir = base_dir / folder if folder else base_dir
    if not target_dir.exists() or not target_dir.is_dir():
        return {"files": [], "total": 0, "skipped": skip, "limit": limit}

    # Collect all files with stats for sorting (this is the expensive operation)
    all_files = []
    for path in target_dir.iterdir():
        if not path.is_file():
            continue
        if scope == "output" and path.name in HIDDEN_OUTPUT_FILENAMES:
            continue
        all_files.append(path)
    
    # Sort by modification time (newest first)
    all_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    total = len(all_files)
    
    # Apply pagination
    paginated_files = all_files[skip : skip + limit]
    
    items = []
    for path in paginated_files:
        relative_path = path.relative_to(base_dir).as_posix()
        stat = path.stat()
        items.append(
            {
                "name": path.name,
                "relativePath": relative_path,
                "folder": folder or "",
                "sizeBytes": stat.st_size,
                "modifiedAt": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "downloadUrl": f"/api/download/{scope}/{quote(relative_path, safe='/')}",
                "extension": path.suffix.lower(),
            }
        )
    
    return {"files": items, "total": total, "skipped": skip, "limit": limit, "hasMore": skip + limit < total}



@app.get("/api/processable-files")
def list_processable_input_files(
    folder: str = Query(...),
    taskType: Literal["process", "download_process", "render_cached", "consistency"] = Query("process"),
) -> dict:
    folder_name = _validate_folder_name(folder)
    target_dir = INPUT_DIR / folder_name
    if not target_dir.exists() or not target_dir.is_dir():
        return {"files": []}

    if taskType == "render_cached":
        return {"files": _list_render_cached_entries(folder_name)}

    last_processed_map = _load_last_processed_map(folder_name)

    files = []
    for path in sorted(p for p in target_dir.iterdir() if p.is_file()):
        ext = path.suffix.lower()
        if ext not in {".docx", ".mhtml", ".pdf"}:
            continue
        if ext in {".docx", ".mhtml"} and "_corrected" in path.name:
            continue
        stat = path.stat()
        files.append(
            {
                "name": path.name,
                "extension": ext,
                "sizeBytes": stat.st_size,
                "modifiedAt": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "lastProcessedAt": last_processed_map.get(path.name),
            }
        )
    return {"files": files}


@app.get("/api/download/{scope}/{relative_path:path}")
def download_file(scope: Literal["input", "output"], relative_path: str) -> FileResponse:
    base_dir = _resolve_scope_root(scope)
    full_path = (base_dir / relative_path).resolve()
    if not str(full_path).startswith(str(base_dir.resolve())) or not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path)


@app.get("/api/download-zip")
def download_directory_zip(
    scope: Literal["input", "output"] = Query("input"),
    folder: str | None = Query(None),
) -> dict:
    base_dir = _resolve_scope_root(scope)
    folder_name = _validate_folder_name(folder) if folder is not None else None
    target_dir = base_dir / folder_name if folder_name else base_dir
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    files = []
    for path in target_dir.iterdir():
        if scope == "output" and path.name in HIDDEN_OUTPUT_DIRNAMES:
            continue
        if not path.is_file():
            continue
        if scope == "output" and path.name in HIDDEN_OUTPUT_FILENAMES:
            continue
        if scope == "output" and ".ai_cache" in path.name:
            continue
        # Avoid self-nesting/recursive growth when archiving output folders.
        if scope == "output" and path.suffix.lower() == ".zip":
            continue
        files.append(path)
    if not files:
        raise HTTPException(status_code=400, detail="No files to archive")

    output_folder = folder_name or "generated"
    archive_output_dir = OUTPUT_DIR / output_folder
    archive_output_dir.mkdir(parents=True, exist_ok=True)
    archive_label = folder_name or scope
    archive_path = _next_available_archive_path(archive_output_dir, f"{archive_label}_{scope}.zip")

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            archive.write(file_path, arcname=file_path.name)

    relative_path = f"{output_folder}/{archive_path.name}" if output_folder else archive_path.name
    return {
        "status": "generated",
        "scope": scope,
        "sourceFolder": folder_name or "",
        "outputFolder": output_folder,
        "outputFile": archive_path.name,
        "outputRelativePath": relative_path,
    }


@app.post("/api/jobs")
def enqueue_job(payload: EnqueueJobRequest) -> dict:
    folder = _validate_folder_name(payload.folder)
    selected_output_types = normalize_output_types(payload.outputTypes or [])
    selected_files = []
    if payload.taskType == "render_cached":
        for token in payload.selectedFiles or []:
            raw_token = str(token or "").strip()
            if not raw_token:
                continue
            selected_files.append(raw_token)
    else:
        for name in payload.selectedFiles or []:
            file_name = Path(str(name or "").strip()).name
            if not file_name or file_name != str(name).strip():
                continue
            selected_files.append(file_name)

    runtime_yaml = load_runtime_yaml()
    yaml_overrides = apply_runtime_yaml_overrides({}, runtime_yaml)

    options = {
        "promptKey": payload.promptKey,
        "outputTypes": selected_output_types,
        "provider": yaml_overrides.get("llm_provider"),
        "model": yaml_overrides.get("llm_model"),
        "llmMaxPasses": yaml_overrides.get("llm_max_passes"),
        "llmMaxConcurrentRequests": yaml_overrides.get("llm_max_concurrent_requests"),
        "llmMaxParallelFiles": yaml_overrides.get("llm_max_parallel_files"),
        "notifyTerminalPunctuation": payload.notifyTerminalPunctuation,
        "urls": payload.urls or "",
        "selectedFiles": sorted(set(selected_files)),
    }

    config_updates = _build_config_updates(
        prompt_key=payload.promptKey,
        output_types=selected_output_types,
        notify_terminal_punctuation=payload.notifyTerminalPunctuation,
    )
    save_config(config_updates)

    job = job_manager.enqueue(payload.taskType, folder, options)
    return {"job": job.to_dict()}


@app.post("/api/preferences")
def save_preferences(payload: SavePreferencesRequest) -> dict:
    config_updates = _build_config_updates(
        prompt_key=payload.promptKey,
        output_types=payload.outputTypes,
        notify_terminal_punctuation=payload.notifyTerminalPunctuation,
    )
    save_config(config_updates)
    return {"status": "ok", "saved": sorted(config_updates.keys())}


@app.get("/api/jobs")
def list_jobs() -> dict:
    return {"jobs": job_manager.list_jobs()}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    try:
        job = job_manager.cancel(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"job": job}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict:
    try:
        job = job_manager.retry(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"job": job}


@app.get("/api/status")
def get_status() -> dict:
    return job_manager.get_status()


@app.get("/api/logs/{kind}")
def get_logs(kind: Literal["execution", "raw", "performance"], lines: int = Query(200, ge=1, le=5000)) -> dict:
    if kind == "execution":
        path = EXECUTION_LOG_PATH
    elif kind == "raw":
        path = RAW_OUTPUT_LOG_PATH
    else:
        path = PERFORMANCE_LOG_PATH
    return {"content": tail_text_file(path, max_lines=lines)}


@app.get("/api/run-state")
def get_run_state() -> dict:
    return job_manager.get_status()


# ============================================================================
# DEBUG & DIAGNOSTICS ENDPOINTS FOR REMOTE SERVERS
# ============================================================================


@app.post("/api/debug/upload")
async def upload_debug_bundle(file: UploadFile = File(...)) -> dict:
    """Accept debug bundle from remote server.
    
    Remote servers capture diagnostics and send them here for analysis.
    Bundles are stored in output/debug_bundles/ for inspection.
    """
    try:
        contents = await file.read()
        filename = Path(file.filename or "debug_bundle.json").name
        
        bundle_path = OUTPUT_DIR / "debug_bundles" / filename
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(bundle_path, "wb") as f:
            f.write(contents)
        
        return {
            "status": "received",
            "filename": filename,
            "size_bytes": len(contents),
            "stored_at": bundle_path.as_posix(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to save debug bundle: {str(e)}")


@app.get("/api/debug/bundles")
def list_debug_bundles(limit: int = Query(20, ge=1, le=100)) -> dict:
    """List recent debug bundles from remote servers."""
    bundles = debug_collector.get_recent_bundles(limit=limit)
    
    result = []
    for bundle_path in bundles:
        try:
            with open(bundle_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            result.append({
                "filename": bundle_path.name,
                "timestamp": data.get("timestamp"),
                "job_id": data.get("job_id"),
                "task_type": data.get("task_type"),
                "status": data.get("status"),
                "size_bytes": bundle_path.stat().st_size,
                "download_url": f"/api/debug/bundles/{bundle_path.name}",
            })
        except Exception:
            pass
    
    return {"bundles": result}


@app.get("/api/debug/bundles/{bundle_filename}")
def download_debug_bundle(bundle_filename: str) -> FileResponse:
    """Download a specific debug bundle for analysis."""
    bundle_path = (OUTPUT_DIR / "debug_bundles" / bundle_filename).resolve()
    
    if not str(bundle_path).startswith(str((OUTPUT_DIR / "debug_bundles").resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    
    if not bundle_path.exists():
        raise HTTPException(status_code=404, detail="Bundle not found")
    
    return FileResponse(bundle_path, filename=bundle_filename)


@app.post("/api/debug/analyze")
async def analyze_debug_bundle(file: UploadFile = File(...)) -> dict:
    """Analyze uploaded debug bundle and return insights.
    
    This processes a debug bundle and extracts actionable diagnostics
    that can be used to identify and fix issues on the remote server.
    """
    try:
        contents = await file.read()
        data = json.loads(contents)
        
        # Extract key diagnostic information
        analysis = {
            "timestamp": data.get("timestamp"),
            "job_id": data.get("job_id"),
            "task_type": data.get("task_type"),
            "status": data.get("status"),
            "issues": [],
            "recommendations": [],
            "system_health": {},
        }
        
        # System diagnostics
        sys_snap = data.get("system_snapshot", {})
        if sys_snap:
            mem = sys_snap.get("memory_usage", {})
            if mem.get("percent", 0) > 85:
                analysis["issues"].append(
                    f"High memory usage: {mem.get('percent', 0)}% "
                    f"({mem.get('available_mb', 0):.0f}MB available)"
                )
                analysis["recommendations"].append(
                    "Consider increasing available memory or breaking processing into smaller batches"
                )
            
            disk = sys_snap.get("disk_usage", {})
            if disk.get("percent", 0) > 90:
                analysis["issues"].append(
                    f"Low disk space: {disk.get('percent', 0)}% used, "
                    f"only {disk.get('free_mb', 0):.0f}MB available"
                )
                analysis["recommendations"].append("Free up disk space on remote server")
            
            analysis["system_health"] = {
                "hostname": sys_snap.get("hostname"),
                "platform": sys_snap.get("platform_info", {}).get("system"),
                "cpu_usage_percent": sys_snap.get("cpu_usage"),
                "memory_usage_percent": mem.get("percent"),
                "disk_usage_percent": disk.get("percent"),
            }
        
        # Error diagnostics
        error_details = data.get("error_details", {})
        if error_details:
            analysis["issues"].append(
                f"Error: {error_details.get('error_type')} - {error_details.get('error_message')}"
            )
            analysis["error_traceback"] = error_details.get("traceback")
        
        # Configuration issues
        runtime_config = data.get("runtime_config", {})
        if not runtime_config.get("llm_provider"):
            analysis["issues"].append("LLM provider not configured")
            analysis["recommendations"].append("Configure LLM_PROVIDER in environment variables")
        
        # Log analysis
        logs = data.get("logs", {})
        execution_log = logs.get("execution_log", "")
        if "Connection refused" in execution_log or "Unable to connect" in execution_log:
            analysis["issues"].append("Failed to connect to LLM provider")
            analysis["recommendations"].append(
                "Verify LLM provider is running and accessible at the configured URL"
            )
        
        # Messages
        messages = data.get("messages", [])
        if messages:
            analysis["recent_messages"] = messages[-5:]  # Last 5 messages
        
        # Performance
        perf = data.get("performance_metrics", {})
        if perf:
            analysis["performance"] = perf
        
        return analysis
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in debug bundle")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.get("/api/debug/health-check")
def debug_health_check() -> dict:
    """System health check for remote server verification.
    
    Remote servers can call this to verify connectivity and baseline diagnostics.
    """
    snapshot = debug_collector.capture_system_snapshot()
    return {
        "status": "ok",
        "timestamp": snapshot.timestamp,
        "hostname": snapshot.hostname,
        "platform": snapshot.platform_info.get("system"),
        "python_version": snapshot.python_version.split()[0],
        "cpu_usage_percent": snapshot.cpu_usage,
        "memory_usage_percent": snapshot.memory_usage.get("percent"),
        "disk_usage_percent": snapshot.disk_usage.get("percent"),
        "api_version": "1.0",
    }


@app.post("/api/debug/test-error")
def test_error_capture() -> dict:
    """Test endpoint to verify error capture is working (dev/debug only).
    
    This intentionally raises an error and captures diagnostics to verify
    the debug collector is functioning correctly.
    """
    try:
        # Simulate an error
        data = {"test": "value"}
        result = data["missing_key"]  # KeyError
    except Exception as e:
        diag = debug_collector.capture_diagnostics(
            job_id="test-error-capture",
            task_type="test",
            status="failed",
            messages=["Test error capture"],
            error=e,
            error_context={"test": "context"},
        )
        bundle_path = debug_collector.save_debug_bundle(diag)
        return {
            "status": "error_captured",
            "bundle": bundle_path.name if bundle_path else None,
            "error_type": type(e).__name__,
        }
    
    return {"status": "no_error"}



@app.get("/api/provider-status")
def get_provider_status() -> dict:
    config = hydrate_runtime_config(load_config())
    foundry_settings = get_azure_ai_foundry_settings(config)
    return {
        "ollama": {"models": fetch_ollama_models()},
        "lmStudio": {
            "baseUrl": get_lm_studio_settings(config).get("base_url"),
            "models": fetch_lm_studio_models(config),
        },
        "azureAiFoundry": {
            "modelName": foundry_settings.get("model_name"),
            "profile": foundry_settings.get("profile"),
            "profiles": [entry.get("profile") for entry in foundry_settings.get("entries", [])],
        },
    }


@app.get("/health")
def health() -> dict:
    return {"ok": True}


def _resolve_scope_root(scope: str) -> Path:
    if scope == "input":
        return INPUT_DIR
    if scope == "output":
        return OUTPUT_DIR
    raise HTTPException(status_code=400, detail="Unsupported scope")


def _validate_folder_name(name: str) -> str:
    folder = (name or "").strip()
    if not folder or any(char in folder for char in ("/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid folder name")
    return folder


def _load_last_processed_map(folder_name: str) -> dict[str, str]:
    state_path = OUTPUT_DIR / folder_name / "summary_report_state.json"
    if not state_path.exists() or not state_path.is_file():
        return {}

    try:
        with open(state_path, "r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)
    except Exception:
        return {}

    runs = payload.get("runs", []) if isinstance(payload, dict) else []
    if not isinstance(runs, list):
        return {}

    last_processed: dict[str, str] = {}
    for run in reversed(runs):
        timestamp = str(run.get("timestamp", "")).strip()
        files = run.get("files", [])
        if not timestamp or not isinstance(files, list):
            continue
        for file_entry in files:
            if not isinstance(file_entry, dict):
                continue
            name = str(file_entry.get("name", "")).strip()
            if name and name not in last_processed:
                last_processed[name] = timestamp
    return last_processed


def _build_current_source_signature(source_path: Path) -> dict[str, int]:
    stat = source_path.stat()
    return {
        "sizeBytes": int(stat.st_size),
        "mtimeNs": int(stat.st_mtime_ns),
    }


def _encode_render_cache_selection_token(prompt_key: str, source_name: str) -> str:
    return f"{RENDER_CACHE_PREFIX}::{prompt_key}::{source_name}"


def _list_render_cached_entries(folder_name: str) -> list[dict]:
    input_dir = INPUT_DIR / folder_name
    cache_root = OUTPUT_DIR / folder_name / ".ai_cache"
    if not cache_root.exists() or not cache_root.is_dir():
        return []

    prompt_defs = get_selectable_prompt_definitions()
    last_processed_map = _load_last_processed_map(folder_name)
    entries: list[dict] = []

    for prompt_dir in sorted(path for path in cache_root.iterdir() if path.is_dir()):
        prompt_key = prompt_dir.name
        prompt_meta = prompt_defs.get(prompt_key, {})
        prompt_name = str(prompt_meta.get("name") or prompt_key)
        for cache_file in sorted(path for path in prompt_dir.iterdir() if path.is_file() and path.suffix.lower() == ".json"):
            try:
                with open(cache_file, "r", encoding="utf-8") as file_handle:
                    payload = json.load(file_handle)
            except Exception:
                continue

            source_name = str(payload.get("sourceFileName") or cache_file.stem).strip()
            if not source_name:
                continue

            source_path = input_dir / source_name
            source_exists = source_path.exists() and source_path.is_file()
            cache_ready = False
            cache_status = "missing_source"
            if source_exists:
                cached_signature = payload.get("sourceSignature") if isinstance(payload.get("sourceSignature"), dict) else {}
                cache_ready = cached_signature == _build_current_source_signature(source_path)
                cache_status = "ready" if cache_ready else "stale"

            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            correction_count = int(summary.get("correctionCount", 0) or 0)
            selection_value = _encode_render_cache_selection_token(prompt_key, source_name)

            entries.append(
                {
                    "name": source_name,
                    "sourceName": source_name,
                    "promptKey": prompt_key,
                    "promptName": prompt_name,
                    "selectionValue": selection_value,
                    "cacheReady": cache_ready,
                    "cacheStatus": cache_status,
                    "cacheSavedAt": payload.get("savedAt"),
                    "lastProcessedAt": last_processed_map.get(source_name),
                    "correctionCount": correction_count,
                }
            )

    entries.sort(
        key=lambda item: (
            item.get("sourceName", "").lower(),
            item.get("promptName", "").lower(),
            item.get("promptKey", "").lower(),
        )
    )
    return entries


def _safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            destination = (target_root / member.filename).resolve()
            if not str(destination).startswith(str(target_root)):
                raise ValueError(f"Unsafe zip entry: {member.filename}")
        archive.extractall(target_root)


def _next_available_archive_path(output_dir: Path, base_filename: str) -> Path:
    """Return a non-colliding ZIP path using a date-time suffix when needed."""
    candidate = output_dir / base_filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix or ".zip"
    timestamp_suffix = datetime.now().strftime("%B_%d_%Y_%I_%M_%S_%p")
    version = 1
    while True:
        version_token = "" if version == 1 else f"_{version}"
        versioned = output_dir / f"{stem}_{timestamp_suffix}{version_token}{suffix}"
        if not versioned.exists():
            return versioned
        version += 1


def _append_execution_log(message: str) -> None:
    timestamp = datetime.now().isoformat()
    with open(EXECUTION_LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] [zip-extract] {message}\n")


def _extract_zip_background(zip_path: Path, target_dir: Path) -> None:
    try:
        _append_execution_log(f"Started extraction: {zip_path.name} -> {target_dir}")
        _safe_extract_zip(zip_path, target_dir)
        _append_execution_log(f"Completed extraction: {zip_path.name}")
    except Exception as exc:
        _append_execution_log(f"Extraction failed for {zip_path.name}: {exc}")


def run_web_server(host: str = "127.0.0.1", port: int = 8000, access_log: bool = False) -> None:
    import uvicorn

    uvicorn.run("local_web:app", host=host, port=port, reload=False, access_log=access_log)


if __name__ == "__main__":
    run_web_server()
