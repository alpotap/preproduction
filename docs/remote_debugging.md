# Remote Debugging Guide

→ [Back to readme.md](../readme.md)

This guide explains how to capture diagnostic information from a remote server and send it back to your local development machine for analysis.

## Overview

When the Document Correction Toolkit runs on a remote server, you need a way to understand what's happening when things go wrong. This debugging system lets you:

- **Capture** system state, configuration, logs, and errors from the remote server
- **Transmit** diagnostic bundles back to your development machine
- **Analyze** issues locally using built-in analysis tools
- **Fix** problems with full context and visibility

## Architecture

The remote debug system has three parts:

1. **Remote Collector** (`toolkit/debug_collector.py`) — Runs on remote server, captures diagnostics
2. **Local API** (`local_web.py` debug endpoints) — Receives and stores bundles, provides analysis
3. **Local Analyzer** (`toolkit/debug_analyzer.py`) — Analyzes bundles and generates reports

## Quick Start

### Setup (One-time)

**On the remote server:**

Ensure `toolkit/debug_collector.py` is available (included in repository).

**On your local machine:**

1. Start the local web server:
   ```powershell
   py .\local_web.py
   ```
   Server runs at `http://127.0.0.1:8000`

2. Verify debug endpoints are available:
   ```powershell
   curl http://127.0.0.1:8000/api/debug/health-check
   ```

### Remote Server: Capture & Send Diagnostics

**Python code on remote server:**

```python
from pathlib import Path
from toolkit.debug_collector import DebugCollector
import requests

# Initialize collector
collector = DebugCollector(output_dir=Path("/path/to/output"))

# At the point of failure, capture diagnostics
try:
    # ... your processing code ...
except Exception as e:
    diagnostics = collector.capture_diagnostics(
        job_id="batch_001",
        task_type="process",
        status="failed",
        messages=["Processing started", "Error during LLM call"],
        error=e,
        error_context={
            "input_file": "document.docx",
            "model_being_used": "gpt-4",
        },
        performance_metrics={
            "elapsed_seconds": 45.2,
            "tokens_processed": 1500,
        },
    )
    
    # Save locally (for backup)
    bundle_path = collector.save_debug_bundle(diagnostics)
    
    # Send to your development machine
    with open(bundle_path, "rb") as f:
        response = requests.post(
            "http://<YOUR_LOCAL_IP>:8000/api/debug/upload",
            files={"file": f},
        )
    print(f"Sent to dev machine: {response.json()}")
```

### Local Machine: Receive & Analyze

**Via Web UI:**

1. Go to http://127.0.0.1:8000
2. Look for "Debug Bundles" section
3. Download and review bundles
4. Upload for analysis to see recommendations

**Via CLI:**

```powershell
# List recent debug bundles
py -m toolkit.debug_analyzer --list -n 15

# Analyze the most recent bundle
py -m toolkit.debug_analyzer latest

# Analyze a specific bundle
py -m toolkit.debug_analyzer output/debug_bundles/debug_job123.json

# Save analysis report to file
py -m toolkit.debug_analyzer latest --save
```

## What Gets Captured

### System Snapshot

- **Hostname, platform, Python version**
- **Resource usage**: CPU %, memory %, disk space
- **Available memory and disk**: To identify resource constraints
- **Environment variables**: Safe subset (excludes API keys)
- **Installed packages**: For dependency mismatch troubleshooting

### Configuration

- **LLM Provider** and **Model** in use
- **Active prompt** settings
- **Input/Output directories**
- **Output types** (inline, track_changes, etc.)

### Logs

- **Execution log**: Last 50 lines of processing activity
- **Raw LLM output log**: Last 50 lines of LLM responses
- **Performance log**: Timing and throughput data

### Error Details

- **Exception type and message**
- **Full traceback**
- **Additional context** passed by the application

### Job Metadata

- **Job ID** for correlation
- **Task type** (process, consistency, download)
- **Status** (queued, running, failed, completed)
- **Progress messages**

## Analysis Output

The local analyzer detects common issues:

### Resource Issues
- 🔴 **Disk full** (>90% used) — immediate action needed
- ⚠️ **High memory** (>85% used) — reduce batch size
- ⚠️ **Low disk** (>80% used) — cleanup recommended

### Configuration Issues
- 🔴 **Missing provider** — LLM provider not configured
- 🔴 **Missing credentials** — Azure API keys missing
- ⚠️ **Localhost URL on remote** — LM Studio URL needs updating

### Connectivity Issues
- 🔴 **Connection refused** — Provider not running/accessible
- ⏱️ **Timeout** — Response too slow, check network
- 🔐 **Authentication failed** — Invalid credentials/expired token

### Processing Issues
- 💾 **Out of memory** — Reduce input size or increase memory
- 📁 **File not found** — Path issues or permissions
- ❌ **Other errors** — Full traceback provided

## Integration Examples

### Wrap Your Processing Loop

```python
from toolkit.debug_collector import DebugCollector
from toolkit.engine import process_files
import requests
import json

collector = DebugCollector()
LOCAL_DEV_URL = "http://<your-ip>:8000"

try:
    process_files(config, input_dir, output_dir, ...)
    
    diagnostics = collector.capture_diagnostics(
        job_id="batch_001",
        task_type="process",
        status="completed",
        messages=["All files processed successfully"],
    )
    
except Exception as e:
    diagnostics = collector.capture_diagnostics(
        job_id="batch_001",
        task_type="process",
        status="failed",
        messages=["Failed to process batch"],
        error=e,
    )
    
    # Send to dev machine
    try:
        bundle = collector.save_debug_bundle(diagnostics)
        with open(bundle, "rb") as f:
            requests.post(f"{LOCAL_DEV_URL}/api/debug/upload", files={"file": f})
    except Exception as send_err:
        print(f"Could not send diagnostics: {send_err}")
    
    raise
```

### Background Job Monitoring

```python
# In web_jobs.py or job processing loop
def run_job(job_id, task_config):
    collector = DebugCollector()
    
    try:
        # Process job
        for step in job_steps:
            # ... do work ...
            pass
        
        final_status = "completed"
        messages = ["Job completed successfully"]
        
    except Exception as e:
        final_status = "failed"
        messages = [f"Failed at step {step}: {str(e)}"]
        error = e
    
    # Always capture diagnostics at end
    diagnostics = collector.capture_diagnostics(
        job_id=job_id,
        task_type=task_config["type"],
        status=final_status,
        messages=messages,
        error=error if final_status == "failed" else None,
    )
    
    # Send to local dev machine
    send_diagnostics_to_local_dev(diagnostics)
```

## API Reference

### POST /api/debug/upload

**Remote server → Local development machine**

Upload a debug bundle JSON file for storage and analysis.

```bash
curl -X POST \
  -F "file=@debug_bundle.json" \
  http://127.0.0.1:8000/api/debug/upload
```

Response:
```json
{
  "status": "received",
  "filename": "debug_job123_failed_2025-03-14T15-45-30.json",
  "size_bytes": 125000,
  "stored_at": "/path/to/output/debug_bundles/debug_job123..."
}
```

### GET /api/debug/bundles

**List recent debug bundles**

```bash
curl http://127.0.0.1:8000/api/debug/bundles?limit=20
```

Response:
```json
{
  "bundles": [
    {
      "filename": "debug_job123_failed_...json",
      "timestamp": "2025-03-14T15:45:30.123456",
      "job_id": "job123",
      "task_type": "process",
      "status": "failed",
      "size_bytes": 125000,
      "download_url": "/api/debug/bundles/debug_job123_failed..."
    }
  ]
}
```

### GET /api/debug/bundles/{filename}

**Download a specific bundle**

```bash
curl http://127.0.0.1:8000/api/debug/bundles/debug_job123_failed.json > bundle.json
```

### POST /api/debug/analyze

**Upload a bundle for immediate analysis**

```bash
curl -X POST \
  -F "file=@debug_bundle.json" \
  http://127.0.0.1:8000/api/debug/analyze
```

Response:
```json
{
  "timestamp": "2025-03-14T15:45:30",
  "job_id": "job123",
  "task_type": "process",
  "status": "failed",
  "issues": [
    "Connection refused to LLM provider at http://ollama:11434/v1",
    "High memory usage: 92% (245MB available)"
  ],
  "recommendations": [
    "Verify Ollama is running on http://ollama:11434",
    "Consider increasing available memory or reducing batch size"
  ],
  "system_health": {
    "hostname": "remote-server-01",
    "platform": "Linux",
    "cpu_usage_percent": 78.5,
    "memory_usage_percent": 92,
    "disk_usage_percent": 87
  }
}
```

### GET /api/debug/health-check

**Verify remote server connectivity**

From remote server:
```bash
curl http://<local-dev-ip>:8000/api/debug/health-check
```

Response:
```json
{
  "status": "ok",
  "timestamp": "2025-03-14T15:45:30",
  "hostname": "dev-machine",
  "platform": "Windows",
  "python_version": "3.9.7",
  "cpu_usage_percent": 15.2,
  "memory_usage_percent": 52.8,
  "disk_usage_percent": 68.3,
  "api_version": "1.0"
}
```

## Troubleshooting

### "Connection refused" from remote server

**Problem:** Remote server can't reach your development machine's debug API.

**Solutions:**
- Make sure local web server is running: `py .\local_web.py`
- Check firewall allows port 8000
- Use actual IP, not localhost: `http://192.168.x.x:8000`
- Test connectivity: `curl http://<your-ip>:8000/api/debug/health-check`

### "Bundle not found" or "No bundles received"

**Problem:** Bundles aren't arriving at local machine.

**Solutions:**
- Check `output/debug_bundles/` directory exists
- Verify POST requests are being made (add logging)
- Check for 400-level HTTP errors in upload response
- Ensure file is valid JSON with `.json` extension

### Sensitive data in bundles

**Privacy concerns:** Environment variables and logs may contain sensitive patterns.

**Mitigations:**
- `DebugCollector` automatically redacts values containing "API_KEY", "SECRET", etc.
- Path values truncated to 200 chars
- Review before sharing bundles outside your organization
- Use HTTPS/secure channels if transmitting over public networks

## Best Practices

1. **Add context** — Pass `error_context` with business meaning (filename, model, inputs)

2. **Use job IDs** — Correlate bundles with application logs using consistent job IDs

3. **Capture at boundaries** — Get diagnostics at process start, after major steps, and on failure

4. **Batch transmission** — Send bundles periodically or after failures, not continuously

5. **Archive old bundles** — Regularly clean up `output/debug_bundles/` to manage disk space

6. **Document issues** — Save analysis reports alongside bundles for reference

7. **Test your path** — Run `/api/debug/health-check` regularly to verify connectivity

## See Also

- [Configuration Guide](configuration.md) — Environment variables and provider setup
- [API Contract](api_contract.md) — Full endpoint reference
- [Troubleshooting Guide](../docs/internal/instructions.md) — Common issues and solutions
