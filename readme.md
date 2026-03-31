# Document Correction Toolkit

This project corrects spelling and grammar in Word documents and web content while keeping document structure and images intact.

## What it does

- Processes `.docx` files directly.
- Converts `.mhtml` files to `.docx` (Windows + MS Word), then processes them.
- Can download URLs to `.mhtml` and process them.
- Inserts empty lines before and after image paragraphs.
- Preserves images while applying text corrections.
- Saves corrected output as `.docx`.
- Logs performance to `output/performance_log.csv`.

## Requirements

- Python 3.9+
- Install dependencies:

```shell
pip install -r requirements.txt
```

- For `.mhtml` conversion on Windows:
    - Microsoft Word installed
    - `pywin32` installed

## Quick start

1. Put input files in `input/`.
2. Run interactive mode:

```shell
py .\process.py
```

3. Follow prompts:
     - Optional URL download from `input/urls.txt`
     - Model selection
     - File selection
4. Find outputs in `output/`.

## Command-line mode

Process a DOCX:

```shell
py .\process.py --source-type docx --input "input\sample.docx"
```

Process an MHTML:

```shell
py .\process.py --source-type mhtml --input "input\sample.mhtml"
```

Download and process a URL:

```shell
py .\process.py --source-type url --input "https://example.com"
```

## Folder layout

- `input/`: source files (`.docx`, `.mhtml`, `urls.txt`)
- `output/`: corrected files and logs
- `process.py`: main entry point
- `document_processor.py`: document text correction and image-safe handling
- `convert.py`: MHTML to DOCX conversion through Word automation

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
Azure API Version: 2025-03-01-preview
Azure Deployment Name: GPT 40 mini (low quality but very fast)
Azure AI Foundry Model Name: gpt-oss-120b
LLM Temperature: 0.1
LLM Max Tokens: 8000

## Model providers

- `ollama`: local model endpoint (`http://localhost:11434/v1`)
- `azure_openai`: Azure OpenAI endpoint (requires Azure environment variables)
- `azure_ai_foundry`: Azure AI Foundry endpoint (requires Azure AI Foundry environment variables, no API version required)

## Environment Variables by Provider

### Ollama
No environment variables needed. Ollama uses local endpoint `http://localhost:11434/v1`.

### Azure OpenAI

**Required environment variables:**

- `AZURE_OPENAI_API_KEY` — Your Azure OpenAI API key (Key 1 or Key 2 from Azure Portal)
- `AZURE_OPENAI_ENDPOINT` — Your Azure OpenAI endpoint (e.g., `https://your-resource-name.openai.azure.com/`)

**Optional environment variable:**

- `AZURE_OPENAI_API_VERSION` — Overrides `Azure API Version` in configuration (default: `2024-10-21`)

**Setup example (PowerShell):**
```powershell
$env:AZURE_OPENAI_API_KEY="your-api-key-here"
$env:AZURE_OPENAI_ENDPOINT="https://your-resource-name.openai.azure.com/"
```

**Permanent setup (PowerShell):**
```powershell
setx AZURE_OPENAI_API_KEY "your-api-key-here"
setx AZURE_OPENAI_ENDPOINT "https://your-resource-name.openai.azure.com/"
```

### Azure AI Foundry

**Required environment variables:**

- `AZURE_AI_FOUNDRY_API_KEY` — Your Azure AI Foundry API key
- `AZURE_AI_FOUNDRY_ENDPOINT` — Your Azure AI Foundry endpoint including `/openai/v1` path (e.g., `https://your-resource.services.ai.azure.com/openai/v1/`)

**Setup example (PowerShell):**
```powershell
$env:AZURE_AI_FOUNDRY_API_KEY="your-foundry-key-here"
$env:AZURE_AI_FOUNDRY_ENDPOINT="https://your-resource.services.ai.azure.com/openai/v1/"
```

**Permanent setup (PowerShell):**
```powershell
setx AZURE_AI_FOUNDRY_API_KEY "your-foundry-key-here"
setx AZURE_AI_FOUNDRY_ENDPOINT "https://your-resource.services.ai.azure.com/openai/v1/"
```

## Verifying Environment Variables

To verify your environment variables are set correctly:

```powershell
# Check if set
echo $env:AZURE_OPENAI_API_KEY
echo $env:AZURE_OPENAI_ENDPOINT
echo $env:AZURE_AI_FOUNDRY_API_KEY
echo $env:AZURE_AI_FOUNDRY_ENDPOINT

# Check just the first character (for security)
echo $env:AZURE_OPENAI_API_KEY[0]
```

If variables don't appear, restart PowerShell after using `setx`.

If provider initialization fails, the tool prints a recovery hint in terminal output.

## Notes on image handling

- Blank lines are inserted before and after image paragraphs before AI processing.
- Paragraphs that include images are updated with image-preserving logic.
- This prevents inline images from being removed during correction.

## Troubleshooting

- No model available:
    - Start Ollama and ensure a model is installed.
- `.mhtml` conversion fails:
    - Ensure Word is installed and `pywin32` is available.
- Azure OpenAI initialization fails:
    - Set `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_ENDPOINT`.
    - Ensure `Azure Deployment Name` matches your deployed model name in Azure OpenAI.
- Azure AI Foundry initialization fails:
    - Set `AZURE_AI_FOUNDRY_API_KEY` and `AZURE_AI_FOUNDRY_ENDPOINT`.
    - Ensure `Azure AI Foundry Model Name` matches your deployed model name in Azure AI Foundry.

## Prompt behavior

Prompts are loaded from `prompts.py` using `Active Prompt` in the configuration section above.
