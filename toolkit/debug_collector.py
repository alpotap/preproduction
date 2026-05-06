"""Remote debugging collector for capturing system diagnostics and runtime state."""

from __future__ import annotations

import json
import argparse
import platform
import shutil
import sys
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import socket

from toolkit.utils import load_config, get_output_root
from toolkit.engine import hydrate_runtime_config
from toolkit.providers import normalize_provider


@dataclass
class SystemSnapshot:
    """Immutable snapshot of system state at a point in time."""

    timestamp: str
    hostname: str
    platform_info: dict[str, str]
    python_version: str
    cpu_usage: float
    memory_usage: dict[str, Any]
    disk_usage: dict[str, Any]
    environment_vars: dict[str, str]
    installed_packages: list[str]


@dataclass
class ProcessingError:
    """Structured error record from a processing job."""

    timestamp: str
    job_id: str
    task_type: str
    folder: str
    error_type: str
    error_message: str
    traceback: str
    system_snapshot: dict[str, Any]
    runtime_config: dict[str, str]
    additional_context: dict[str, Any]


@dataclass
class RuntimeDiagnostics:
    """Complete diagnostics bundle for transmission to debug tools."""

    timestamp: str
    job_id: str
    task_type: str
    status: str  # queued, running, completed, failed
    messages: list[str]
    system_snapshot: dict[str, Any]
    runtime_config: dict[str, str]
    logs: dict[str, str]  # execution log, raw output log fragments
    error_details: Optional[dict[str, Any]]
    performance_metrics: Optional[dict[str, Any]]


class DebugCollector:
    """Captures and serializes diagnostic information from runtime failures."""

    def __init__(self, output_dir: Path = None):
        """Initialize collector.

        Args:
            output_dir: Where to write debug bundles. Defaults to configured output root.
        """
        self.output_dir = output_dir or get_output_root()
        self.debug_dir = self.output_dir / "debug_bundles"
        self.debug_dir.mkdir(exist_ok=True, parents=True)

    def capture_system_snapshot(self) -> SystemSnapshot:
        """Capture current system state."""
        try:
            psutil = self._load_psutil()
            disk = shutil.disk_usage(self.output_dir)
            memory_usage: dict[str, Any] = {}
            cpu_usage = 0.0
            if psutil is not None:
                mem = psutil.virtual_memory()
                cpu_usage = psutil.cpu_percent(interval=1)
                memory_usage = {
                    "percent": mem.percent,
                    "available_mb": mem.available / (1024 * 1024),
                    "used_mb": mem.used / (1024 * 1024),
                    "total_mb": mem.total / (1024 * 1024),
                }

            return SystemSnapshot(
                timestamp=datetime.now().isoformat(),
                hostname=socket.gethostname(),
                platform_info={
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine(),
                    "processor": platform.processor(),
                },
                python_version=sys.version,
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                disk_usage={
                    "percent": (disk.used / disk.total) * 100 if disk.total else 0.0,
                    "free_mb": disk.free / (1024 * 1024),
                    "used_mb": disk.used / (1024 * 1024),
                    "total_mb": disk.total / (1024 * 1024),
                },
                environment_vars=self._safe_env_vars(),
                installed_packages=self._get_installed_packages(),
            )
        except Exception as e:
            print(f"[DEBUG] Failed to capture system snapshot: {e}")
            return self._minimal_snapshot()

    def _load_psutil(self):
        try:
            import psutil  # type: ignore

            return psutil
        except ImportError:
            return None

    def _safe_env_vars(self) -> dict[str, str]:
        """Capture relevant environment variables, excluding secrets."""
        import os

        safe_keys = {
            "PATH",
            "PYTHON",
            "TEMP",
            "TMP",
            "COMPUTERNAME",
            "USERNAME",
            "OS",
            "PATHEXT",
            "SYSTEMROOT",
            "LANG",
            "LANGUAGE",
        }
        # Also capture provider hints (not actual keys)
        provider_keys = {k for k in os.environ if "PROVIDER" in k.upper() or "LLM" in k.upper()}

        captured = {}
        for key in safe_keys | provider_keys:
            if key in os.environ:
                val = os.environ[key]
                # Mask paths containing sensitive patterns
                if any(
                    pattern in val.lower()
                    for pattern in ["api_key", "secret", "password", "token"]
                ):
                    captured[key] = "*REDACTED*"
                else:
                    captured[key] = val[:200]  # Truncate long values

        return captured

    def _get_installed_packages(self) -> list[str]:
        """Get list of installed packages."""
        try:
            import pkg_resources

            return sorted(
                [
                    f"{d.project_name}=={d.version}"
                    for d in pkg_resources.working_set
                ]
            )
        except Exception:
            return []

    def _minimal_snapshot(self) -> SystemSnapshot:
        """Fallback snapshot when capture fails."""
        return SystemSnapshot(
            timestamp=datetime.now().isoformat(),
            hostname="unknown",
            platform_info={"system": platform.system()},
            python_version=sys.version,
            cpu_usage=0.0,
            memory_usage={},
            disk_usage={},
            environment_vars={},
            installed_packages=[],
        )

    def capture_error(
        self,
        job_id: str,
        task_type: str,
        folder: str,
        error: Exception,
        context: dict[str, Any] = None,
        runtime_config: dict[str, Any] = None,
    ) -> ProcessingError:
        """Capture a processing error with full context.

        Args:
            job_id: Unique job identifier
            task_type: Type of task (process, analyze, etc.)
            folder: Processing folder
            error: The exception that occurred
            context: Additional diagnostic data

        Returns:
            ProcessingError record ready for serialization
        """
        snapshot = self.capture_system_snapshot()
        config = runtime_config or hydrate_runtime_config(load_config() or {})

        return ProcessingError(
            timestamp=datetime.now().isoformat(),
            job_id=job_id,
            task_type=task_type,
            folder=folder,
            error_type=type(error).__name__,
            error_message=str(error),
            traceback=traceback.format_exc(),
            system_snapshot=asdict(snapshot),
            runtime_config=config,
            additional_context=context or {},
        )

    def capture_diagnostics(
        self,
        job_id: str,
        task_type: str,
        status: str,
        messages: list[str] = None,
        error: Exception = None,
        error_context: dict[str, Any] = None,
        performance_metrics: dict[str, Any] = None,
        runtime_config: dict[str, Any] = None,
    ) -> RuntimeDiagnostics:
        """Capture complete runtime diagnostics.

        Args:
            job_id: Unique job identifier
            task_type: Task type
            status: Job status (queued, running, completed, failed, etc.)
            messages: Progress or diagnostic messages
            error: Exception if status is 'failed'
            error_context: Additional error context
            performance_metrics: Timing and throughput data

        Returns:
            RuntimeDiagnostics bundle
        """
        snapshot = self.capture_system_snapshot()
        config = runtime_config or hydrate_runtime_config(load_config() or {})
        logs = self._collect_recent_logs()

        error_details = None
        if error:
            err_record = self.capture_error(
                job_id,
                task_type,
                "",
                error,
                error_context,
                runtime_config=config,
            )
            error_details = asdict(err_record)

        diag = RuntimeDiagnostics(
            timestamp=datetime.now().isoformat(),
            job_id=job_id,
            task_type=task_type,
            status=status,
            messages=messages or [],
            system_snapshot=asdict(snapshot),
            runtime_config=config,
            logs=logs,
            error_details=error_details,
            performance_metrics=performance_metrics or {},
        )

        return diag

    def _collect_recent_logs(self) -> dict[str, str]:
        """Collect recent log entries from output files."""
        logs = {}

        log_files = [
            ("execution_log", self.output_dir / "execution.log"),
            ("raw_output_log", self.output_dir / "llm_raw_output.log"),
            ("performance_log", self.output_dir / "performance_log.csv"),
        ]

        for name, path in log_files:
            try:
                if path.exists():
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        # Get last 50 lines
                        lines = f.readlines()[-50:]
                        logs[name] = "".join(lines)
            except Exception as e:
                logs[name] = f"[ERROR reading log: {e}]"

        return logs

    def save_debug_bundle(self, diagnostics: RuntimeDiagnostics) -> Path:
        """Save diagnostics bundle to file for remote transmission.

        Args:
            diagnostics: RuntimeDiagnostics to save

        Returns:
            Path to saved bundle
        """
        filename = (
            f"debug_{diagnostics.job_id}_{diagnostics.status}"
            f"_{datetime.now().isoformat().replace(':', '-')}.json"
        )
        bundle_path = self.debug_dir / filename

        try:
            # Convert dataclass to dict
            bundle_data = asdict(diagnostics) if hasattr(diagnostics, "__dataclass_fields__") else diagnostics.__dict__

            with open(bundle_path, "w", encoding="utf-8") as f:
                json.dump(bundle_data, f, indent=2, default=str)

            print(f"[DEBUG] Bundle saved to: {bundle_path}")
            return bundle_path

        except Exception as e:
            print(f"[ERROR] Failed to save debug bundle: {e}")
            return None

    def export_for_analysis(self, diagnostics: RuntimeDiagnostics) -> str:
        """Export diagnostics as formatted text for analysis."""
        lines = [
            "=" * 80,
            "REMOTE DIAGNOSTICS BUNDLE",
            "=" * 80,
            "",
            f"Timestamp: {diagnostics.timestamp}",
            f"Job ID: {diagnostics.job_id}",
            f"Task Type: {diagnostics.task_type}",
            f"Status: {diagnostics.status}",
            "",
            "--- MESSAGES ---",
            "\n".join(diagnostics.messages) if diagnostics.messages else "(none)",
            "",
            "--- SYSTEM SNAPSHOT ---",
            json.dumps(diagnostics.system_snapshot, indent=2),
            "",
            "--- CONFIGURATION ---",
            json.dumps(diagnostics.runtime_config, indent=2),
            "",
            "--- LOGS (Last 50 lines per file) ---",
        ]

        for log_name, log_content in diagnostics.logs.items():
            lines.append(f"\n[{log_name}]")
            lines.append(log_content)

        if diagnostics.error_details:
            lines.append("")
            lines.append("--- ERROR DETAILS ---")
            lines.append(json.dumps(diagnostics.error_details, indent=2))

        if diagnostics.performance_metrics:
            lines.append("")
            lines.append("--- PERFORMANCE METRICS ---")
            lines.append(json.dumps(diagnostics.performance_metrics, indent=2))

        lines.append("")
        lines.append("=" * 80)

        return "\n".join(lines)

    def get_recent_bundles(self, limit: int = 10) -> list[Path]:
        """Get recent debug bundles."""
        bundles = sorted(self.debug_dir.glob("debug_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return bundles[:limit]


def _load_latest_job_context(output_dir: Path) -> dict[str, Any]:
    """Load most recent job metadata from web job history when available."""
    history_path = output_dir / "web_job_history.json"
    if not history_path.exists():
        return {}
    try:
        with open(history_path, "r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        if not jobs:
            return {}
        latest = jobs[-1]
        if not isinstance(latest, dict):
            return {}
        return {
            "job_id": str(latest.get("id") or "").strip(),
            "task_type": str(latest.get("taskType") or "").strip(),
            "status": str(latest.get("status") or "").strip(),
            "message": str(latest.get("currentMessage") or "").strip(),
            "error": str(latest.get("error") or "").strip(),
            "provider": str((latest.get("options") or {}).get("provider") or "").strip(),
            "model": str((latest.get("options") or {}).get("model") or "").strip(),
        }
    except Exception:
        return {}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a runtime diagnostics bundle.")
    parser.add_argument("--job-id", default="", help="Job identifier stored in the bundle")
    parser.add_argument("--task-type", default="", help="Task type label stored in the bundle")
    parser.add_argument(
        "--status",
        default="",
        choices=["queued", "running", "completed", "failed", "canceled"],
        help="Execution status stored in the bundle",
    )
    parser.add_argument(
        "--message",
        action="append",
        default=[],
        help="Optional message to include. Repeat for multiple lines.",
    )
    parser.add_argument(
        "--error-message",
        default="",
        help="Optional error text to include as error_details.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional override for output root (defaults to configured output root).",
    )
    parser.add_argument(
        "--capture-only",
        action="store_true",
        help="Capture a bundle only; skip immediate analysis output.",
    )
    parser.add_argument(
        "--provider",
        default="",
        help="Optional runtime provider override for captured config (e.g., azure_ai_foundry).",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Optional runtime model override for captured config (e.g., profile::model).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else get_output_root()
    collector = DebugCollector(output_dir=output_dir)
    latest_job = _load_latest_job_context(output_dir)

    job_id = args.job_id.strip() or latest_job.get("job_id") or "manual_debug"
    task_type = args.task_type.strip() or latest_job.get("task_type") or "manual"
    status = (args.status or "").strip() or latest_job.get("status") or "failed"
    messages = args.message or []
    if not messages and latest_job.get("message"):
        messages = [latest_job["message"]]

    runtime_config = hydrate_runtime_config(load_config() or {})
    effective_provider = args.provider.strip() or latest_job.get("provider") or ""
    effective_model = args.model.strip() or latest_job.get("model") or ""
    if effective_provider:
        runtime_config["llm_provider"] = effective_provider
    if effective_model:
        runtime_config["llm_model"] = effective_model
    if effective_provider and not effective_model:
        runtime_config = hydrate_runtime_config(runtime_config)
    runtime_config["llm_provider"] = normalize_provider(runtime_config.get("llm_provider", ""))

    error_message = args.error_message.strip() or latest_job.get("error") or ""
    error = RuntimeError(error_message) if error_message else None
    diagnostics = collector.capture_diagnostics(
        job_id=job_id,
        task_type=task_type,
        status=status,
        messages=messages,
        error=error,
        runtime_config=runtime_config,
    )
    bundle_path = collector.save_debug_bundle(diagnostics)
    if not bundle_path:
        return 1
    if args.capture_only:
        return 0

    from toolkit.debug_analyzer import DebugAnalyzer

    analyzer = DebugAnalyzer(output_dir=output_dir)
    bundle = analyzer.load_bundle(bundle_path)
    analysis = analyzer.analyze_bundle(bundle)
    report = analyzer.format_report(analysis)
    print()
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
