# Configuration and Environment Guide

→ [Back to readme.md](../readme.md)

This page contains runtime keys, provider configuration, and environment setup.

## Remote debugging support

Remote diagnostics do not require extra runtime keys in `readme.md`.

If `psutil` is installed, debug bundles include richer CPU and memory metrics. Without it, the application still runs and diagnostics fall back to basic disk and environment information.

For the fullest diagnostics on another host, install the full dependency set from `requirements.txt`.

## Runtime configuration (read from readme.md)

The tool reads the Configuration section in [readme.md](../readme.md). Keep each line as `Key: value`.

Current keys:

- Language
- Input Directory
- Output Directory
- Highlight Corrections
- Add Comments
- Active Prompt
- LLM Provider
- LLM Model
- LM Studio Base URL
- LM Studio Model Name
- Azure API Version
- Azure Deployment Name
- Azure AI Foundry Model Name
- LLM Temperature
- LLM Max Tokens
- Output Types

Notes:
- `Output Types` controls only corrected document formats.
- Summary report artifacts (`summary_report_state.json` and `summary_report.docx`) are generated automatically from execution statistics and do not require additional configuration keys.

## Windows service configuration

When the web UI is installed as a Windows service, startup settings are written to `output/web_service_config.json`.

Current service settings:

- `host`
- `port`
- `access_log`

These settings are managed by `Register-WebService.ps1`, not by the `readme.md` runtime key section.

## Provider configuration

Supported providers:

- Ollama
- LM Studio
- Azure OpenAI
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

### Azure OpenAI

Required:

```powershell
$env:AZURE_OPENAI_API_KEY = "your-api-key"
$env:AZURE_OPENAI_ENDPOINT = "https://your-resource.openai.azure.com/"
```

Optional:

```powershell
$env:AZURE_OPENAI_API_VERSION = "2024-10-21"
```

Permanent setup:

```powershell
setx AZURE_OPENAI_API_KEY "your-api-key"
setx AZURE_OPENAI_ENDPOINT "https://your-resource.openai.azure.com/"
setx AZURE_OPENAI_API_VERSION "2024-10-21"
```

Set `Azure Deployment Name` in [readme.md](../readme.md) to the deployment name in your Azure OpenAI resource.

### Azure AI Foundry

Required:

```powershell
$env:AZURE_AI_FOUNDRY_API_KEY = "your-foundry-key"
$env:AZURE_AI_FOUNDRY_ENDPOINT = "https://your-resource.services.ai.azure.com/openai/v1/"
```

Permanent setup:

```powershell
setx AZURE_AI_FOUNDRY_API_KEY "your-foundry-key"
setx AZURE_AI_FOUNDRY_ENDPOINT "https://your-resource.services.ai.azure.com/openai/v1/"
```

Set `Azure AI Foundry Model Name` in [readme.md](../readme.md) to your deployed model name.

## Verify environment variables

```powershell
echo $env:LM_STUDIO_BASE_URL
echo $env:AZURE_OPENAI_API_KEY
echo $env:AZURE_OPENAI_ENDPOINT
echo $env:AZURE_AI_FOUNDRY_API_KEY
echo $env:AZURE_AI_FOUNDRY_ENDPOINT
```

If values are missing after `setx`, restart the terminal session.

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
