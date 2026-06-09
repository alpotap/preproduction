"""Background job queue for the local web UI and future API integrations."""

from __future__ import annotations

import contextlib
import queue
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import json

from toolkit.utils import get_input_root, get_output_root, load_config, set_windows_hidden
from toolkit.engine import (
    hydrate_runtime_config,
    initialize_client_for_config,
    list_processable_files,
    process_files,
    run_consistency_for_course,
    get_parallel_file_runtime_telemetry,
)
from toolkit.llm_service import get_llm_request_runtime_telemetry
from toolkit.web_tools import download_url_as_mhtml

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = get_input_root()
OUTPUT_DIR = get_output_root()
EXECUTION_LOG_PATH = OUTPUT_DIR / "execution.log"
RAW_OUTPUT_LOG_PATH = OUTPUT_DIR / "llm_raw_output.log"
PERFORMANCE_LOG_PATH = OUTPUT_DIR / "performance_log.csv"
JOB_HISTORY_PATH = OUTPUT_DIR / "web_job_history.json"
HIDDEN_OUTPUT_ARTIFACTS = (
    OUTPUT_DIR / "debug_bundles",
    EXECUTION_LOG_PATH,
    PERFORMANCE_LOG_PATH,
    JOB_HISTORY_PATH,
)


@dataclass
class JobRecord:
    """In-memory representation of one queued or running job."""

    id: str
    task_type: str
    folder: str
    options: dict[str, Any]
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    current_message: str = "Queued"
    error: str | None = None
    processed_files: int = 0
    downloaded_urls: int = 0
    output_count: int = 0
    correction_count: int = 0
    total_input_tokens: int = 0
    total_tokens_generated: int = 0
    total_tokens: int = 0
    retries: int = 0
    parent_job_id: str | None = None
    cancel_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "taskType": self.task_type,
            "folder": self.folder,
            "status": self.status,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "currentMessage": self.current_message,
            "error": self.error,
            "processedFiles": self.processed_files,
            "downloadedUrls": self.downloaded_urls,
            "outputCount": self.output_count,
            "correctionCount": self.correction_count,
            "totalInputTokens": self.total_input_tokens,
            "totalTokensGenerated": self.total_tokens_generated,
            "totalTokens": self.total_tokens,
            "retries": self.retries,
            "parentJobId": self.parent_job_id,
            "cancelRequested": self.cancel_requested,
            "options": self.options,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobRecord":
        return cls(
            id=str(payload.get("id", str(uuid.uuid4()))),
            task_type=str(payload.get("taskType", "process")),
            folder=str(payload.get("folder", "")),
            options=dict(payload.get("options") or {}),
            status=str(payload.get("status", "queued")),
            created_at=str(payload.get("createdAt", datetime.now().isoformat())),
            started_at=payload.get("startedAt"),
            finished_at=payload.get("finishedAt"),
            current_message=str(payload.get("currentMessage", "Queued")),
            error=payload.get("error"),
            processed_files=int(payload.get("processedFiles", 0) or 0),
            downloaded_urls=int(payload.get("downloadedUrls", 0) or 0),
            output_count=int(payload.get("outputCount", 0) or 0),
            correction_count=int(payload.get("correctionCount", 0) or 0),
            total_input_tokens=int(payload.get("totalInputTokens", 0) or 0),
            total_tokens_generated=int(payload.get("totalTokensGenerated", 0) or 0),
            total_tokens=int(payload.get("totalTokens", 0) or 0),
            retries=int(payload.get("retries", 0) or 0),
            parent_job_id=payload.get("parentJobId"),
            cancel_requested=bool(payload.get("cancelRequested", False)),
        )


class _TeeLogWriter:
    """Mirror job output to console and append it to the execution log."""

    def __init__(self, manager: "JobQueueManager", job_id: str):
        self.manager = manager
        self.job_id = job_id
        self._buffer = ""

    @property
    def encoding(self) -> str | None:
        return getattr(sys.__stdout__, "encoding", None)

    @property
    def errors(self) -> str | None:
        return getattr(sys.__stdout__, "errors", None)

    def write(self, text: str) -> int:
        if not text:
            return 0
        sys.__stdout__.write(text)
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self.manager.record_line(self.job_id, line)
        return len(text)

    def flush(self) -> None:
        sys.__stdout__.flush()
        if self._buffer:
            self.manager.record_line(self.job_id, self._buffer)
            self._buffer = ""

    def isatty(self) -> bool:
        return bool(getattr(sys.__stdout__, "isatty", lambda: False)())

    def writable(self) -> bool:
        return True

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False

    def fileno(self) -> int:
        return sys.__stdout__.fileno()

    def __getattr__(self, name: str):
        return getattr(sys.__stdout__, name)


class JobQueueManager:
    """Single-worker FIFO queue that runs long jobs in the background."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._job_order: list[str] = []
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._current_job_id: str | None = None
        self._canceled_queue_job_ids: set[str] = set()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "debug_bundles").mkdir(parents=True, exist_ok=True)
        self._ensure_hidden_output_artifacts()
        self._restore_state()
        self._worker = threading.Thread(target=self._worker_loop, name="web-job-worker", daemon=True)
        self._worker.start()

    def _ensure_hidden_output_artifacts(self) -> None:
        for target in HIDDEN_OUTPUT_ARTIFACTS:
            if target.exists():
                set_windows_hidden(target, hidden=True)

    def enqueue(self, task_type: str, folder: str, options: dict[str, Any]) -> JobRecord:
        job = JobRecord(id=str(uuid.uuid4()), task_type=task_type, folder=folder, options=options)
        with self._lock:
            self._jobs[job.id] = job
            self._job_order.append(job.id)
            self._save_state_locked()
        self._queue.put(job.id)
        self.record_line(job.id, f"Job queued: type={task_type} folder={folder}")
        return job

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError("Job not found")
            if job.status == "queued":
                job.status = "canceled"
                job.finished_at = datetime.now().isoformat()
                job.current_message = "Canceled before execution"
                job.error = None
                self._canceled_queue_job_ids.add(job_id)
                self._save_state_locked()
                return job.to_dict()
            if job.status == "running":
                job.cancel_requested = True
                job.current_message = "Cancellation requested; waiting for safe checkpoint"
                self._save_state_locked()
                return job.to_dict()
            raise ValueError(f"Cannot cancel job in status '{job.status}'")

    def retry(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            prior = self._jobs.get(job_id)
            if not prior:
                raise KeyError("Job not found")
            if prior.status not in {"failed", "canceled", "completed"}:
                raise ValueError(f"Cannot retry job in status '{prior.status}'")
            retried = JobRecord(
                id=str(uuid.uuid4()),
                task_type=prior.task_type,
                folder=prior.folder,
                options=dict(prior.options),
                retries=prior.retries + 1,
                parent_job_id=prior.id,
                current_message="Queued from retry",
            )
            self._jobs[retried.id] = retried
            self._job_order.append(retried.id)
            self._save_state_locked()
        self._queue.put(retried.id)
        self.record_line(retried.id, f"Retry queued from {job_id}")
        return retried.to_dict()

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._jobs[job_id].to_dict() for job_id in reversed(self._job_order)]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_dict() if job else None

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            queued = sum(1 for job in self._jobs.values() if job.status == "queued")
            running = self._jobs.get(self._current_job_id).to_dict() if self._current_job_id else None
            parallel_metrics = get_parallel_file_runtime_telemetry()
            llm_metrics = get_llm_request_runtime_telemetry()
            return {
                "currentRun": running,
                "queueLength": self._queue.qsize(),
                "queuedJobs": queued,
                "totalJobs": len(self._jobs),
                "telemetry": {
                    "activeParallelFileWorkers": parallel_metrics.get("activeParallelFileWorkers", 0),
                    "peakParallelFileWorkers": parallel_metrics.get("peakParallelFileWorkers", 0),
                    "llmInflightRequests": llm_metrics.get("inflight", 0),
                    "llmQueueWaiters": llm_metrics.get("waiting", 0),
                    "averageQueueWaitMs": llm_metrics.get("averageWaitMs", 0.0),
                },
            }

    def record_line(self, job_id: str, message: str) -> None:
        line = message.rstrip()
        if not line:
            return
        # Ignore uvicorn access-log noise captured during redirected stdout.
        if '/api/' in line and 'HTTP/1.1' in line:
            return
        timestamp = datetime.now().isoformat()
        formatted = f"[{timestamp}] [{job_id}] {line}"
        # Clear hidden flag before writing to avoid permission issues on some network shares.
        set_windows_hidden(EXECUTION_LOG_PATH, hidden=False)
        with open(EXECUTION_LOG_PATH, "a", encoding="utf-8") as log_file:
            log_file.write(formatted + "\n")
        set_windows_hidden(EXECUTION_LOG_PATH, hidden=True)
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.current_message = line
                self._save_state_locked()

    def _set_job_state(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in updates.items():
                setattr(job, key, value)
            self._save_state_locked()

    def _cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            return bool(job and job.cancel_requested)

    def _raise_if_cancel_requested(self, job_id: str) -> None:
        if self._cancel_requested(job_id):
            raise RuntimeError("Canceled by user request")

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            with self._lock:
                if job_id in self._canceled_queue_job_ids:
                    self._canceled_queue_job_ids.remove(job_id)
                    self._queue.task_done()
                    continue
                job = self._jobs.get(job_id)
                if not job:
                    self._queue.task_done()
                    continue
            with self._lock:
                self._current_job_id = job_id
                self._jobs[job_id].status = "running"
                self._jobs[job_id].started_at = datetime.now().isoformat()
                self._jobs[job_id].current_message = "Starting job"
                self._save_state_locked()
            try:
                self._run_job(job_id)
                self._set_job_state(
                    job_id,
                    status="completed",
                    finished_at=datetime.now().isoformat(),
                    current_message="Completed",
                    cancel_requested=False,
                )
                self.record_line(job_id, "Job completed")
            except Exception as exc:
                is_canceled = str(exc) == "Canceled by user request"
                self._set_job_state(
                    job_id,
                    status="canceled" if is_canceled else "failed",
                    finished_at=datetime.now().isoformat(),
                    current_message="Canceled" if is_canceled else "Failed",
                    error=None if is_canceled else str(exc),
                    cancel_requested=False,
                )
                if is_canceled:
                    self.record_line(job_id, "Job canceled")
                else:
                    self.record_line(job_id, f"Job failed: {exc}")
            finally:
                with self._lock:
                    self._current_job_id = None
                    self._save_state_locked()
                self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            task_type = job.task_type
            folder = job.folder
            options = dict(job.options)

        source_dir = INPUT_DIR / folder
        source_dir.mkdir(parents=True, exist_ok=True)
        output_dir = OUTPUT_DIR / folder
        output_dir.mkdir(parents=True, exist_ok=True)

        config = hydrate_runtime_config(load_config())
        self._apply_job_overrides(config, options)

        writer = _TeeLogWriter(self, job_id)
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            self.record_line(job_id, f"Initializing client for provider {config['llm_provider']}")
            self._raise_if_cancel_requested(job_id)
            client = initialize_client_for_config(config)

            selected_names = {str(name).strip() for name in options.get("selectedFiles", []) if str(name).strip()}

            if task_type == "download_process":
                files_before = {path.name for path in list_processable_files(source_dir)}
                urls = [line.strip() for line in str(options.get("urls", "")).splitlines() if line.strip()]
                self.record_line(job_id, f"Downloading {len(urls)} URL(s)")
                downloaded_count = 0
                for url in urls:
                    self._raise_if_cancel_requested(job_id)
                    downloaded = download_url_as_mhtml(url, source_dir)
                    if downloaded:
                        downloaded_count += 1
                self._set_job_state(job_id, downloaded_urls=downloaded_count)

                files_after = {path.name for path in list_processable_files(source_dir)}
                new_files = files_after - files_before
                selected_names = selected_names.union(new_files)

            if task_type == "consistency":
                self.record_line(job_id, f"Running consistency analysis for folder {folder}")
                self._raise_if_cancel_requested(job_id)
                result = run_consistency_for_course(source_dir, Path(config["output_dir"]), folder, config, WORKSPACE_DIR)
                self.record_line(job_id, f"Consistency analysis written to {result['analysis_docx']}")
                self._set_job_state(
                    job_id,
                    output_count=1,
                    correction_count=0,
                    total_input_tokens=0,
                    total_tokens_generated=0,
                    total_tokens=0,
                )
                return

            files_to_process = list_processable_files(source_dir)
            if selected_names:
                files_to_process = [path for path in files_to_process if path.name in selected_names]

            self._set_job_state(job_id, processed_files=len(files_to_process))
            if not files_to_process:
                if task_type == "download_process":
                    raise RuntimeError(
                        "No new processable files found for Download/Upload and process. "
                        "Add a new upload or URL and try again."
                    )
                if selected_names:
                    raise RuntimeError(
                        f"No selected files found in input/{folder}. Refresh files and try again."
                    )
                raise RuntimeError(f"No processable files found in input/{folder}.")

            self.record_line(job_id, f"Processing {len(files_to_process)} file(s)")
            self._raise_if_cancel_requested(job_id)
            run_result = process_files(
                files_to_process,
                config,
                client,
                WORKSPACE_DIR,
                output_dir=output_dir,
                cleanup_source_mhtml=True,
                should_cancel=lambda: self._cancel_requested(job_id),
            )

            correction_count = int((run_result or {}).get("correctionCount", 0) or 0)
            total_input_tokens = int((run_result or {}).get("totalInputTokens", 0) or 0)
            total_tokens_generated = int((run_result or {}).get("totalTokensGenerated", 0) or 0)
            total_tokens = total_input_tokens + total_tokens_generated

            output_count = sum(1 for path in output_dir.rglob("*") if path.is_file())
            self._set_job_state(
                job_id,
                output_count=output_count,
                correction_count=correction_count,
                total_input_tokens=total_input_tokens,
                total_tokens_generated=total_tokens_generated,
                total_tokens=total_tokens,
            )

    def _restore_state(self) -> None:
        if not JOB_HISTORY_PATH.exists():
            return
        with open(JOB_HISTORY_PATH, "r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        for job_payload in jobs:
            job = JobRecord.from_dict(job_payload)
            if job.status in {"queued", "running"}:
                job.status = "queued"
                job.started_at = None
                job.finished_at = None
                job.cancel_requested = False
                job.current_message = "Requeued after service restart"
                self._queue.put(job.id)
            self._jobs[job.id] = job
            self._job_order.append(job.id)

    def _save_state_locked(self) -> None:
        payload = {
            "savedAt": datetime.now().isoformat(),
            "jobs": [self._jobs[job_id].to_dict() for job_id in self._job_order],
        }
        # Clear hidden flag before writing to avoid permission issues on some network shares.
        set_windows_hidden(JOB_HISTORY_PATH, hidden=False)
        with open(JOB_HISTORY_PATH, "w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle, indent=2)
        set_windows_hidden(JOB_HISTORY_PATH, hidden=True)

    def _apply_job_overrides(self, config: dict[str, Any], options: dict[str, Any]) -> None:
        prompt_key = options.get("promptKey")
        output_types = options.get("outputTypes")
        provider = options.get("provider")
        model = options.get("model")
        llm_max_concurrent_requests = options.get("llmMaxConcurrentRequests")
        llm_max_parallel_files = options.get("llmMaxParallelFiles")
        llm_max_passes = options.get("llmMaxPasses")
        notify_terminal_punctuation = options.get("notifyTerminalPunctuation")

        if prompt_key:
            config["active_prompt"] = prompt_key
        if output_types:
            config["output_types"] = output_types
        if provider:
            config["llm_provider"] = provider
        if model:
            config["llm_model"] = model
            if provider == "lm_studio":
                config["lm_studio_model_name"] = model
        if llm_max_concurrent_requests is not None:
            try:
                config["llm_max_concurrent_requests"] = max(1, min(20, int(llm_max_concurrent_requests)))
            except (TypeError, ValueError):
                pass
        if llm_max_parallel_files is not None:
            try:
                config["llm_max_parallel_files"] = max(1, min(8, int(llm_max_parallel_files)))
            except (TypeError, ValueError):
                pass
        if llm_max_passes is not None:
            try:
                config["llm_max_passes"] = max(1, min(5, int(llm_max_passes)))
            except (TypeError, ValueError):
                pass
        if notify_terminal_punctuation is not None:
            config["notify_terminal_punctuation"] = bool(notify_terminal_punctuation)


def tail_text_file(path: Path, max_lines: int = 200) -> str:
    """Return the last max_lines from a text file, or an empty string if missing."""
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as file_handle:
        lines = file_handle.readlines()
    return "".join(lines[-max_lines:])


job_manager = JobQueueManager()
