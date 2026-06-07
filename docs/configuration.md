# Configuration and Environment Guide

→ [Back to readme.md](../readme.md)

This page contains runtime keys, provider configuration, and environment setup.

## Input and output folders

Input and output roots are configured only in `paths.json` at the repository root.

Example:

```json
{
    "input_dir": "input",
    "output_dir": "output"
}
```

Rules:

- Relative paths are resolved from the repository root.
- Absolute paths are allowed.
- CLI and web use the same file.
- The wizard and web UI do not offer path editing and do not persist path changes.

## Remote debugging support

Remote diagnostics do not require extra runtime keys in `readme.md`.

If `psutil` is installed, debug bundles include richer CPU and memory metrics. Without it, the application still runs and diagnostics fall back to basic disk and environment information.

For the fullest diagnostics on another host, install the full dependency set from `requirements.txt`.

## Runtime configuration (read from readme.md)

The tool reads the Configuration section in [readme.md](../readme.md). Keep each line as `Key: value`.

Current keys:

- Language
- Highlight Corrections
- Add Comments
- Active Prompt
- LLM Provider
- LLM Model
- LM Studio Base URL
- LM Studio Model Name
- LLM Temperature
- LLM Max Tokens
- LLM Max Passes
- Notify Terminal Punctuation
- Output Types
- AI Only Corrections
- Retry On Empty Corrections

Azure AI Foundry endpoint, API key, and API version settings are environment-only.

Notes:
- `Output Types` controls only corrected document formats.
- `AI Only Corrections` defaults to `true` and keeps correction output strictly model-provided (no local augmentation of extra corrections).
- Set `AI Only Corrections: false` only when you explicitly want legacy local post-processing/augmentation behavior.
- Objective guardrails still apply in both modes: invalid terminal appends like `?.`, `!.`, and `:.` are dropped.
- `LLM Max Passes` defaults to `1` and caps total correction attempts per chunk (allowed range `1` to `5`).
- `Retry On Empty Corrections` defaults to `true`. When enabled, the low-temperature empty-result retry is counted inside `LLM Max Passes` (it is not an unlimited extra pass).
- `Notify Terminal Punctuation` controls whether terminal-punctuation explanations are inserted as comments.
- Terminal punctuation suppression strings are loaded from `terminal_punctuation_suppress_strings.txt` in the repository root. Use one string per line; lines starting with `#` are treated as comments.
- `Input Directory` and `Output Directory` are no longer read from `readme.md`; use `paths.json` instead.
- Summary report artifacts (`summary_report_state.json` and `summary_report.docx`) are generated automatically from execution statistics and do not require additional configuration keys.
- Raw LLM logging writes both request input and response output to `output/llm_raw_output.log`, and the file is automatically trimmed to a maximum size of 10 MB.
- Each raw log entry also includes single-line `input_preview` and `output_preview` fields near the end of the entry so tail views can show both directions even when full payloads are large.
- CLI and web both persist provider/model/prompt/output-type defaults into this shared section, so choices apply across browser sessions and users on the same host.
- Invisible Unicode whitespace (non-breaking spaces, zero-width characters, etc.) in source documents is automatically normalized before LLM analysis. This is transparent and requires no configuration.
- Correction sanitation blocks duplicate terminal punctuation artifacts (for example `..`) during list-item period augmentation and application.
- Prompt templates include explicit versions (`version`, baseline `1.0`) and are loaded from `prompts/prod` and `prompts/staging`.
- Preferred authoring format is `*.prompt.md` (metadata header + prompt text body).
- Startup automatically regenerates prompt JSON artifacts from markdown.
- Prompt category labels are for selection/grouping and do not change processing mode by themselves.
- Promotion from staging to production is manual by copying a prompt file from `prompts/staging` to `prompts/prod`.
- If multiple production versions exist in one lineage, only the latest production version is exposed in user selection lists.
- Markdown files are the source of truth for prompt edits.
- Staging markdown filenames are normalized to include the version suffix automatically.
- Prompt names exposed to CLI/web selection include version in the display name.

## Windows service configuration

When the web UI is installed as a Windows service, startup settings are written to `output/web_service_config.json`.

The `output` portion of that path follows the root configured in `paths.json`.

Current service settings:

- `host`
- `port`
- `access_log`

These settings are managed by `Register-WebService.ps1`, not by the `readme.md` runtime key section.

## Provider configuration

Supported providers:

- Ollama
- LM Studio
- Azure AI Foundry

### Ollama

No environment variables required.
Default endpoint: http://localhost:11434/v1

### LM Studio

Start LM Studio local server and load a model.

Optional override:

```powershell
$env:LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
```

### Azure AI Foundry

Preferred method: interactive setup script.

```bash
python setup_foundry_env.py
```

If Python launcher is available, this also works:

```bash
py setup_foundry_env.py
```

The script opens an interactive menu where you can:

1. List configured models with masked API keys.
2. Add a model profile.
3. Edit an existing model profile.
4. Remove a model profile.
5. Test a model with a basic API call.
6. Save to both USER and MACHINE environment variables by default (run elevated).

Model count is unlimited.

Each profile stores:

1. Display name (used in CLI/web lists).
2. Model/deployment name (used in API calls).
3. API key.
4. API version (default: `2025-01-01-preview`).
5. Endpoint.
6. Vendor category (for provider grouping in CLI/web).

It then writes the full Azure AI Foundry environment variable set for you (including profile variables and vendor/display metadata) and loads the values in the current terminal session.

Scope options:

- Default: BOTH scopes (`HKCU\\Environment` and `HKLM`) for consistent multi-user usage.
- `--scope user`: USER scope only (`HKCU\\Environment`) for local, non-admin scenarios.
- `--scope machine`: MACHINE scope only (`HKLM`) for service/host-level usage.

Examples:

```powershell
py .\setup_foundry_env.py
py .\setup_foundry_env.py --scope user
```

The API key is found in the Azure AI Foundry portal under your project → **Settings → API keys**.

Endpoint formats:

- Azure OpenAI-style resources: `https://<resource-name>.cognitiveservices.azure.com/`
- Azure AI Foundry serverless resources: `https://<resource-name>.services.ai.azure.com/openai/v1/`

For Azure OpenAI-style resources, do **not** include a specific deployment path or `api-version` query string in the endpoint.
For Azure AI Foundry serverless resources, prefer the OpenAI-compatible `.../openai/v1/` base URL shown in Azure.

## Advanced manual setup (optional)

Use this only when you need explicit variable control.

```powershell
$env:AZURE_AI_FOUNDRY_PROFILE_IDS = "primary,secondary"

$env:AZURE_AI_FOUNDRY_PRIMARY_API_KEY = "<key-1>"
$env:AZURE_AI_FOUNDRY_PRIMARY_ENDPOINT = "https://resource-one.cognitiveservices.azure.com/"
$env:AZURE_AI_FOUNDRY_PRIMARY_MODEL_NAME = "gpt-4o-mini"
$env:AZURE_AI_FOUNDRY_PRIMARY_DISPLAY_NAME = "gpt-4o-mini"
$env:AZURE_AI_FOUNDRY_PRIMARY_VENDOR = "Azure"
$env:AZURE_AI_FOUNDRY_PRIMARY_API_VERSION = "2025-01-01-preview"

$env:AZURE_AI_FOUNDRY_SECONDARY_API_KEY = "<key-2>"
$env:AZURE_AI_FOUNDRY_SECONDARY_ENDPOINT = "https://resource-two.cognitiveservices.azure.com/"
$env:AZURE_AI_FOUNDRY_SECONDARY_MODEL_NAME = "gpt-4.1-mini"
$env:AZURE_AI_FOUNDRY_SECONDARY_DISPLAY_NAME = "gpt-4.1-mini"
$env:AZURE_AI_FOUNDRY_SECONDARY_VENDOR = "Azure"
$env:AZURE_AI_FOUNDRY_SECONDARY_API_VERSION = "2025-01-01-preview"
```

For profile IDs, use letters, numbers, and underscore only.

## Verify environment variables

```powershell
$profilesUser = [Environment]::GetEnvironmentVariable("AZURE_AI_FOUNDRY_PROFILE_IDS", "User")
$profilesMachine = [Environment]::GetEnvironmentVariable("AZURE_AI_FOUNDRY_PROFILE_IDS", "Machine")
Write-Host "User Profiles: $profilesUser"
Write-Host "Machine Profiles: $profilesMachine"
```

If values are missing, run `python setup_foundry_env.py` again.

## Remote host notes

- When the app runs on a remote machine, do not use `127.0.0.1` for services that actually live elsewhere.
- For LM Studio, set `LM_STUDIO_BASE_URL` to the real reachable host URL if the model server is not on the same machine.
- To return diagnostics to a developer workstation, point the remote helper at `http://<developer-ip>:8000` and verify `/api/debug/health-check` first.
- Full operator instructions are in [remote_debugging.md](remote_debugging.md).

## Windows service notes

- Run `Register-WebService.ps1` from an elevated PowerShell session.
- Use `-InstallRequirements` on first install after clone so the service host has all Python packages available.
- If you bind to `0.0.0.0` for network access, consider adding `-OpenFirewall` during install.
- Service logs are written to `output/web_service.log` and `output/web_service_error.log`.

Those log paths also follow the output root from `paths.json`.
