# Document Correction Toolkit

Corrects Word documents (.docx, .mhtml, .pdf) and web URLs using an LLM, and generates one or more review-ready output formats from each correction pass.

Each processing run also updates a deterministic summary report from execution statistics (no additional LLM call): `summary_report_state.json` and `summary_report.docx`.

## Requirements

- Python 3.9+
- Microsoft Word (Windows) — required for MHTML and PDF input conversion
- `pip install -r requirements.txt`

## Getting started

**Interactive CLI wizard** — guided session in the terminal:

```shell
py .\process.py
```

See [docs/wizard.md](docs/wizard.md) for the full wizard walkthrough, CLI flags, prompt options, and output formats.

**Local web interface** — browser UI with queue, file browser, and logs:

```shell
py .\local_web.py
```

**Windows background service** — install once, auto-start on reboot:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\Register-WebService.ps1 -Action Install -InstallRequirements
```

See [docs/webapp.md](docs/webapp.md) for the full web UI guide and restart instructions.

See [docs/configuration.md](docs/configuration.md) for environment variables and runtime configuration.

## Folder layout

| Path | Purpose |
|---|---|
| `input/<folder>/` | Source DOCX, MHTML, PDF files |
| `output/<folder>/` | Corrected output files |
| `output/<folder>/summary_report_state.json` | Historical run/correction statistics sidecar |
| `output/<folder>/summary_report.docx` | Auto-generated summary report from sidecar state |
| `output/performance_log.csv` | Per-run performance metrics |
| `output/execution.log` | Background job log |
| `input/urls.txt` | Optional URL list for download jobs |

## Architecture

| File | Role |
|---|---|
| `process.py` | CLI entry point |
| `local_web.py` | Localhost FastAPI server |
| `toolkit/` | Internal processing package used by CLI and web entrypoints |
| `docs/api_contract.md` | Stable v1 API endpoint reference |

## LLM providers

Supported: Ollama, LM Studio, Azure OpenAI, Azure AI Foundry.

Environment variable setup for all providers: [docs/configuration.md](docs/configuration.md).

## Project docs

- Runtime and environment setup: [docs/configuration.md](docs/configuration.md)
- Frontend and localhost usage: [docs/webapp.md](docs/webapp.md)
- Windows service deployment: [docs/webapp.md](docs/webapp.md#windows-service-deployment)
- CLI wizard and processing flow: [docs/wizard.md](docs/wizard.md)
- API contract: [docs/api_contract.md](docs/api_contract.md)
- **Remote debugging** (capture errors from production servers): [docs/remote_debugging.md](docs/remote_debugging.md)
- Contributing guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security reporting: [SECURITY.md](SECURITY.md)

## Configuration

This section is read by the tool at runtime. Keep keys and formatting as `Key: value`.

Language: en-US
Input Directory: input
Output Directory: output
Highlight Corrections: true
Add Comments: true
Active Prompt: default
LLM Provider: azure_ai_foundry
LLM Model: gpt-oss-120b
LM Studio Base URL: http://127.0.0.1:1234/v1
LM Studio Model Name:
Azure API Version: 2025-03-01-preview
Azure Deployment Name: GPT 40 mini (low quality but very fast)
Azure AI Foundry Model Name: gpt-oss-120b
LLM Temperature: 0.1
LLM Max Tokens: 8000
Output Types: inline, uncommented, track_changes, hybrid
