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

This setup wizard now writes Azure AI Foundry variables to both USER and MACHINE scopes by default for consistent multi-user behavior.
Run from an elevated PowerShell session.
For local-only, non-admin scenarios, you can opt into USER-only scope:

```shell
py setup_foundry_env.py --scope user
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

The setup wizard now supports listing configured models, add/edit/remove flows, vendor categories, and an inline model connectivity test.

## Prompt Staging and Versioning

- Prompt templates are loaded from filesystem catalogs:
	- Preferred (human-editable): `prompts/prod/*.prompt.md` and `prompts/staging/*.prompt.md`
	- Startup-generated runtime artifacts: `prompts/generated/prod/*.json` and `prompts/generated/staging/*.json`
- Every prompt now includes `version`, with current default `1.0`.
- A `staging` prompt category is loaded from `prompts/staging` for safe testing.
- `prompt_category` is for selection/grouping only; runtime behavior is controlled by prompt metadata such as `output_mode`.
- Promotion is manual by file copy from `prompts/staging` to `prompts/prod`.
- When multiple production versions exist in one prompt lineage, user selection surfaces show only the latest production version.

Prompt authoring workflow:

- Edit prompt files directly in `*.prompt.md` format (simple metadata header + plain-text prompt body).
- Markdown files are the source of truth.
- On startup/reload, the app automatically generates matching `.json` prompt files into `prompts/generated/` so runtime components always have current JSON artifacts without cluttering authoring folders.
- Staging prompt markdown filenames are automatically normalized to include explicit versions (example: `default_v1_1.prompt.md`) so copied variants stay easy to identify and edit.
- Prompt labels shown in CLI and web include version in the prompt name.
- Runtime sanitation now blocks duplicate terminal punctuation artifacts (for example `..`) when list-item period fixes are augmented/applied.

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
| `output/llm_raw_output.log` | Raw LLM entries with input and output blocks (capped at 10 MB) |

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
Notify Terminal Punctuation: false
Active Prompt: default_v1_4
LLM Provider: azure_ai_foundry
LLM Model:
LM Studio Base URL: http://127.0.0.1:1234/v1
LM Studio Model Name:
LLM Temperature: 0.1
LLM Max Tokens: 8000
LLM Max Passes: 1
Output Types: inline, uncommented, track_changes, hybrid
AI Only Corrections: true
Retry On Empty Corrections: true

Terminal punctuation comment suppression strings are loaded from `terminal_punctuation_suppress_strings.txt` in the repository root. Use one string per line; blank lines and lines starting with `#` are ignored.
