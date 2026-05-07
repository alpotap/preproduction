# Document Correction Toolkit

This repository is a Windows-first document processing tool that:

1. Reads DOCX, MHTML, and PDF files (plus optional URL downloads).
2. Sends text through an LLM correction workflow.
3. Produces review-ready outputs (inline, uncommented, track changes, hybrid).
4. Writes a deterministic summary report from execution stats.

If you are new here, start with the 5-minute setup below.

## Start Here (5 Minutes)

1. Install dependencies.

```shell
py -m pip install -r requirements.txt
```

2. Configure your LLM provider.

```shell
py setup_foundry_env.py
```

3. Choose how you want to run the app.

CLI wizard:

```shell
py .\process.py
```

Web app:

```shell
py .\local_web.py
```

4. Set your shared input/output roots in `paths.json`.

Example:

```json
{
	"input_dir": "input",
	"output_dir": "output"
}
```

You can use relative paths (resolved from the repo root) or absolute paths. CLI and web both honor this file. The wizard and web UI do not edit it.

5. Put files under an input folder and run a job.

Example input location:

```text
input\0123\
```

6. Check results under output.

Example output location:

```text
output\0123\
```

## What Runs What

- [process.py](process.py): interactive CLI entrypoint.
- [local_web.py](local_web.py): local FastAPI server + web UI.
- [run_web.bat](run_web.bat): convenience launcher for local web server on Windows.
- [toolkit/](toolkit): shared core logic used by both CLI and web.

## Providers

Supported providers:

- Ollama
- LM Studio
- Azure AI Foundry

Setup details are in [docs/configuration.md](docs/configuration.md).

For Azure AI Foundry on Windows, quickest path is:

```shell
py setup_foundry_env.py
```

## Where Files Go

The input/output roots come from `paths.json`.

| Path | Purpose |
|---|---|
| `input/<folder>/` | Source DOCX, MHTML, PDF files |
| `input/urls.txt` | Optional URL list for download jobs |
| `output/<folder>/` | Corrected output files |
| `output/<folder>/summary_report_state.json` | Historical run/correction stats |
| `output/<folder>/summary_report.docx` | Auto-generated summary report |
| `output/performance_log.csv` | Per-run performance metrics |
| `output/execution.log` | Background job log |

## Docs Map

- [docs/configuration.md](docs/configuration.md): environment and provider setup.
- [docs/wizard.md](docs/wizard.md): CLI flow, prompts, outputs, troubleshooting.
- [docs/webapp.md](docs/webapp.md): web app usage and service deployment.
- [docs/api_contract.md](docs/api_contract.md): API endpoints and payloads.
- [docs/remote_debugging.md](docs/remote_debugging.md): remote diagnostics workflow.
- [CONTRIBUTING.md](CONTRIBUTING.md): contribution workflow.
- [SECURITY.md](SECURITY.md): security reporting.

## Runtime Configuration

This section is read at runtime. Keep exact `Key: value` formatting.

Provider, model, prompt, and output type defaults are shared across CLI and web for all users because they are persisted in this section.

Language: en-US
Highlight Corrections: true
Add Comments: true
Active Prompt: default
LLM Provider: azure_ai_foundry
LLM Model:
LM Studio Base URL: http://127.0.0.1:1234/v1
LM Studio Model Name:
LLM Temperature: 0.1
LLM Max Tokens: 8000
Output Types: hybrid
