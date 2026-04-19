"""Quick-start helper for enabling debug diagnostics on remote servers.

This script makes it easy to wrap your existing processing pipeline with debug
collection, without needing to modify your application code extensively.

Usage:
    # In your remote processing script:
    from remote_debug_helper import enable_debug, send_diagnostics
    
    enable_debug(output_dir="/path/to/output", dev_machine_url="http://192.168.x.x:8000")
    
    try:
        # your processing code here
        result = process_document(doc)
    except Exception as e:
        send_diagnostics(job_id="batch_001", task_type="process", error=e)
        raise
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
import requests

_debug_enabled = False
_collector = None
_dev_url = None
_job_context = {}


def enable_debug(
    output_dir: Path | str = None,
    dev_machine_url: str = None,
) -> None:
    """Enable debug collection globally.

    Args:
        output_dir: Where to store debug bundles locally (defaults to ./output)
        dev_machine_url: URL of development machine API (e.g., http://192.168.x.x:8000)
    """
    global _debug_enabled, _collector, _dev_url

    try:
        from toolkit.debug_collector import DebugCollector

        output_dir = Path(output_dir or Path.cwd() / "output")
        _collector = DebugCollector(output_dir)
        _dev_url = dev_machine_url
        _debug_enabled = True

        print(f"[DEBUG] Enabled. Bundles → {output_dir / 'debug_bundles'}")
        if _dev_url:
            print(f"[DEBUG] Dev machine: {_dev_url}")
        return

    except ImportError:
        print("[ERROR] toolkit.debug_collector not found. Cannot enable debug.")
        _debug_enabled = False


def set_job_context(job_id: str, task_type: str = None, **kwargs) -> None:
    """Set job context for all diagnostics (used as defaults).

    Args:
        job_id: Unique job identifier
        task_type: Type of task (process, consistency, etc.)
        **kwargs: Additional context (passed to error_context)
    """
    global _job_context

    _job_context = {
        "job_id": job_id,
        "task_type": task_type or "unknown",
        "context": kwargs,
    }


def send_diagnostics(
    job_id: str = None,
    task_type: str = None,
    status: str = "failed",
    messages: list[str] = None,
    error: Exception = None,
    error_context: dict = None,
    performance_metrics: dict = None,
    upload_to_dev: bool = True,
) -> Path:
    """Capture and send diagnostics bundle.

    Args:
        job_id: Job identifier (uses context if not provided)
        task_type: Task type (uses context if not provided)
        status: Job status (queued, running, completed, failed)
        messages: List of progress messages
        error: Exception if status is 'failed'
        error_context: Additional error context
        performance_metrics: Timing/throughput data
        upload_to_dev: Whether to send to dev machine (True) or just save locally (False)

    Returns:
        Path to saved bundle
    """
    if not _debug_enabled or not _collector:
        print("[DEBUG] Debug not enabled, skipping diagnostics")
        return None

    # Use context defaults
    job_id = job_id or _job_context.get("job_id", "unknown")
    task_type = task_type or _job_context.get("task_type", "unknown")

    # Merge error context
    ctx = error_context or {}
    ctx.update(_job_context.get("context", {}))

    # Capture
    diagnostics = _collector.capture_diagnostics(
        job_id=job_id,
        task_type=task_type,
        status=status,
        messages=messages or [],
        error=error,
        error_context=ctx,
        performance_metrics=performance_metrics or {},
    )

    # Save locally
    bundle_path = _collector.save_debug_bundle(diagnostics)

    # Send to dev machine
    if upload_to_dev and _dev_url and bundle_path:
        try:
            with open(bundle_path, "rb") as f:
                response = requests.post(f"{_dev_url}/api/debug/upload", files={"file": f}, timeout=10)
                if response.status_code == 200:
                    print(f"[DEBUG] Sent to {_dev_url}: {response.json().get('filename')}")
                else:
                    print(f"[DEBUG] Upload failed (HTTP {response.status_code})")
        except Exception as e:
            print(f"[DEBUG] Could not send to dev machine: {e}")

    return bundle_path


def send_completion(
    job_id: str = None,
    task_type: str = None,
    messages: list[str] = None,
    performance_metrics: dict = None,
) -> Path:
    """Send successful completion diagnostics.

    Args:
        job_id: Job identifier
        task_type: Task type
        messages: Completion messages
        performance_metrics: Timing data

    Returns:
        Path to saved bundle
    """
    return send_diagnostics(
        job_id=job_id,
        task_type=task_type,
        status="completed",
        messages=messages or ["Completed successfully"],
        error=None,
        performance_metrics=performance_metrics,
    )


def get_recent_bundles(limit: int = 10) -> list[Path]:
    """Get recent locally-saved debug bundles."""
    if not _debug_enabled or not _collector:
        return []
    return _collector.get_recent_bundles(limit=limit)


def print_debug_status() -> None:
    """Print current debug configuration."""
    print("\n" + "=" * 60)
    print("DEBUG STATUS")
    print("=" * 60)
    print(f"Enabled:        {_debug_enabled}")
    if _debug_enabled:
        print(f"Output dir:     {_collector.output_dir if _collector else 'N/A'}")
        print(f"Dev machine:    {_dev_url or 'Not configured'}")
        print(f"Job context:    {_job_context}")
        bundles = get_recent_bundles(limit=5)
        print(f"Recent bundles: {len(bundles)}")
        for b in bundles[:3]:
            print(f"  - {b.name}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    # Test/demo
    enable_debug(dev_machine_url="http://127.0.0.1:8000")
    set_job_context(job_id="test-001", task_type="test", document="sample.docx")

    print_debug_status()

    # Simulate error capture
    try:
        raise ValueError("Sample error for testing")
    except Exception as e:
        bundle = send_diagnostics(
            messages=["Test job started", "Error occurred"],
            error=e,
            upload_to_dev=False,  # Don't upload if testing
        )
        print(f"Bundle saved but not uploaded: {bundle}")
