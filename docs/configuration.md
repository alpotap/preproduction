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
- Output Types

Azure AI Foundry endpoint, API key, and API version settings are environment-only.

Notes:
- `Output Types` controls only corrected document formats.
- `Input Directory` and `Output Directory` are no longer read from `readme.md`; use `paths.json` instead.
- Summary report artifacts (`summary_report_state.json` and `summary_report.docx`) are generated automatically from execution statistics and do not require additional configuration keys.
- CLI and web both persist provider/model/prompt/output-type defaults into this shared section, so choices apply across browser sessions and users on the same host.
- Invisible Unicode whitespace (non-breaking spaces, zero-width characters, etc.) in source documents is automatically normalized before LLM analysis. This is transparent and requires no configuration.

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

The script asks for only 4 values per AI entry:

1. Name
2. API key
3. API version (default: `2025-01-01-preview`)
4. Endpoint

It then writes the full Azure AI Foundry environment variable set for you (including profile variables) and loads the values in the current terminal session.

The API key is found in the Azure AI Foundry portal under your project → **Settings → API keys**.

The endpoint base URL follows the pattern:
`https://<resource-name>.cognitiveservices.azure.com/`

Do **not** include a specific deployment path or `api-version` query string in the endpoint — the SDK appends those automatically.

## Advanced manual setup (optional)

Use this only when you need explicit variable control.

```powershell
$env:AZURE_AI_FOUNDRY_PROFILE_IDS = "primary,secondary"

$env:AZURE_AI_FOUNDRY_PRIMARY_API_KEY = "<key-1>"
$env:AZURE_AI_FOUNDRY_PRIMARY_ENDPOINT = "https://resource-one.cognitiveservices.azure.com/"
$env:AZURE_AI_FOUNDRY_PRIMARY_MODEL_NAME = "gpt-4o-mini"
$env:AZURE_AI_FOUNDRY_PRIMARY_API_VERSION = "2025-01-01-preview"

$env:AZURE_AI_FOUNDRY_SECONDARY_API_KEY = "<key-2>"
$env:AZURE_AI_FOUNDRY_SECONDARY_ENDPOINT = "https://resource-two.cognitiveservices.azure.com/"
$env:AZURE_AI_FOUNDRY_SECONDARY_MODEL_NAME = "gpt-4.1-mini"
$env:AZURE_AI_FOUNDRY_SECONDARY_API_VERSION = "2025-01-01-preview"
```

For profile IDs, use letters, numbers, and underscore only.

## Verify environment variables

```powershell
$profiles = [Environment]::GetEnvironmentVariable("AZURE_AI_FOUNDRY_PROFILE_IDS", "User")
Write-Host "Profiles: $profiles"

foreach ($p in ($profiles -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
    $up = $p.ToUpperInvariant()
    $endpoint = [Environment]::GetEnvironmentVariable("AZURE_AI_FOUNDRY_${up}_ENDPOINT", "User")
    $model = [Environment]::GetEnvironmentVariable("AZURE_AI_FOUNDRY_${up}_MODEL_NAME", "User")
    Write-Host ("{0} => model={1}; endpoint={2}" -f $p, $model, $endpoint)
}
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
