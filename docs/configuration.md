# Configuration and Environment Guide

→ [Back to readme.md](../readme.md)

This page contains runtime keys, provider configuration, and environment setup.

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
