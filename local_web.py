"""Local FastAPI server hosting a single-page UI for the document processing tool."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import quote
import threading
import zipfile
import tempfile

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from pydantic import BaseModel

from toolkit.utils import load_config, save_config
from toolkit.engine import hydrate_runtime_config, PROMPT_DEFINITIONS
from toolkit.output_types import OUTPUT_TYPE_REGISTRY, normalize_output_types, serialize_output_types
from toolkit.providers import (
    OLLAMA_PROVIDER,
    LM_STUDIO_PROVIDER,
    AZURE_PROVIDER,
    AZURE_AI_FOUNDRY_PROVIDER,
    fetch_ollama_models,
    fetch_lm_studio_models,
    get_azure_settings,
    get_azure_ai_foundry_settings,
    get_lm_studio_settings,
)
from toolkit.web_jobs import (
    EXECUTION_LOG_PATH,
    RAW_OUTPUT_LOG_PATH,
    PERFORMANCE_LOG_PATH,
    WORKSPACE_DIR,
    job_manager,
    tail_text_file,
)

APP_TITLE = "Document Correction Toolkit"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
STATIC_DIR = WORKSPACE_DIR / "webapp" / "static"
INPUT_DIR = WORKSPACE_DIR / "input"
OUTPUT_DIR = WORKSPACE_DIR / "output"

app = FastAPI(title=APP_TITLE)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class CreateFolderRequest(BaseModel):
    name: str


class EnqueueJobRequest(BaseModel):
    taskType: Literal["process", "download_process", "consistency"]
    folder: str
    promptKey: str | None = None
    outputTypes: list[str] | None = None
    provider: str | None = None
    model: str | None = None
    urls: str | None = None
    selectedFiles: list[str] | None = None


def _build_prompt_details(prompt_definition: dict) -> str:
    details: list[str] = []
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
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/capabilities")
def get_capabilities() -> dict:
    config = hydrate_runtime_config(load_config())
    return {
        "config": {
            "llmProvider": config.get("llm_provider"),
            "llmModel": config.get("llm_model"),
            "activePrompt": config.get("active_prompt"),
            "outputTypes": config.get("output_types"),
        },
        "prompts": [
            {
                "key": key,
                "abbr": value.get("abbr", ""),
                "name": value.get("name", key),
                "summary": value.get("summary", ""),
                "details": _build_prompt_details(value),
            }
            for key, value in PROMPT_DEFINITIONS.items()
        ],
        "outputTypes": [
            {
                "key": key,
                "label": meta["label"],
                "suffix": meta["suffix"],
            }
            for key, meta in OUTPUT_TYPE_REGISTRY.items()
        ],
        "providers": [
            {"key": OLLAMA_PROVIDER, "label": "Ollama"},
            {"key": LM_STUDIO_PROVIDER, "label": "LM Studio"},
            {"key": AZURE_PROVIDER, "label": "Azure OpenAI"},
            {"key": AZURE_AI_FOUNDRY_PROVIDER, "label": "Azure AI Foundry"},
        ],
    }


@app.get("/api/models")
def get_models(provider: str = Query(...)) -> dict:
    config = hydrate_runtime_config(load_config())
    provider = provider.strip().lower()
    if provider == OLLAMA_PROVIDER:
        models = fetch_ollama_models()
    elif provider == LM_STUDIO_PROVIDER:
        models = fetch_lm_studio_models(config)
    elif provider == AZURE_PROVIDER:
        deployment_name = get_azure_settings(config).get("deployment_name")
        models = [deployment_name] if deployment_name else []
    elif provider == AZURE_AI_FOUNDRY_PROVIDER:
        model_name = get_azure_ai_foundry_settings(config).get("model_name")
        models = [model_name] if model_name else []
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")
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
) -> dict:
    base_dir = _resolve_scope_root(scope)
    target_dir = base_dir / folder if folder else base_dir
    if not target_dir.exists() or not target_dir.is_dir():
        return {"files": []}

    items = []
    for path in sorted((p for p in target_dir.iterdir() if p.is_file()), key=lambda item: item.stat().st_mtime, reverse=True):
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
    return {"files": items}


@app.get("/api/processable-files")
def list_processable_input_files(folder: str = Query(...)) -> dict:
    folder_name = _validate_folder_name(folder)
    target_dir = INPUT_DIR / folder_name
    if not target_dir.exists() or not target_dir.is_dir():
        return {"files": []}

    files = []
    for path in sorted(p for p in target_dir.iterdir() if p.is_file()):
        ext = path.suffix.lower()
        if ext not in {".docx", ".mhtml", ".pdf"}:
            continue
        if ext in {".docx", ".mhtml"} and "_corrected" in path.name:
            continue
        files.append(path.name)
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
) -> FileResponse:
    base_dir = _resolve_scope_root(scope)
    target_dir = base_dir / folder if folder else base_dir
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    files = [path for path in target_dir.iterdir() if path.is_file()]
    if not files:
        raise HTTPException(status_code=400, detail="No files to archive")

    archive_label = folder or scope
    with tempfile.NamedTemporaryFile(prefix=f"{archive_label}_", suffix=".zip", delete=False) as temp_file:
        temp_zip_path = Path(temp_file.name)

    with zipfile.ZipFile(temp_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            archive.write(file_path, arcname=file_path.name)

    return FileResponse(
        temp_zip_path,
        filename=f"{archive_label}.zip",
        background=BackgroundTask(lambda: temp_zip_path.unlink(missing_ok=True)),
    )


@app.post("/api/jobs")
def enqueue_job(payload: EnqueueJobRequest) -> dict:
    folder = _validate_folder_name(payload.folder)
    selected_output_types = normalize_output_types(payload.outputTypes or [])
    selected_files = []
    for name in payload.selectedFiles or []:
        file_name = Path(str(name or "").strip()).name
        if not file_name or file_name != str(name).strip():
            continue
        selected_files.append(file_name)

    options = {
        "promptKey": payload.promptKey,
        "outputTypes": selected_output_types,
        "provider": payload.provider,
        "model": payload.model,
        "urls": payload.urls or "",
        "selectedFiles": sorted(set(selected_files)),
    }

    config_updates: dict[str, str] = {
        "output_types": serialize_output_types(selected_output_types),
    }
    if payload.promptKey:
        config_updates["active_prompt"] = payload.promptKey
    if payload.provider:
        config_updates["llm_provider"] = payload.provider

    model_value = str(payload.model or "").strip()
    if model_value:
        config_updates["llm_model"] = model_value
        if payload.provider == LM_STUDIO_PROVIDER:
            config_updates["lm_studio_model_name"] = model_value

    save_config(config_updates)

    job = job_manager.enqueue(payload.taskType, folder, options)
    return {"job": job.to_dict()}


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


@app.get("/api/provider-status")
def get_provider_status() -> dict:
    config = hydrate_runtime_config(load_config())
    return {
        "ollama": {"models": fetch_ollama_models()},
        "lmStudio": {
            "baseUrl": get_lm_studio_settings(config).get("base_url"),
            "models": fetch_lm_studio_models(config),
        },
        "azureOpenAI": {"deploymentName": get_azure_settings(config).get("deployment_name")},
        "azureAiFoundry": {"modelName": get_azure_ai_foundry_settings(config).get("model_name")},
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


def _safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            destination = (target_root / member.filename).resolve()
            if not str(destination).startswith(str(target_root)):
                raise ValueError(f"Unsafe zip entry: {member.filename}")
        archive.extractall(target_root)


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("local_web:app", host="127.0.0.1", port=8000, reload=False, access_log=False)
