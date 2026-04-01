# Document Correction Toolkit

This project corrects spelling and grammar in Word documents and web content while keeping document structure and images intact.

## What it does

- Processes `.docx` files directly.
- Converts `.mhtml` files to `.docx` (Windows + MS Word), then processes them.
- Converts `.pdf` files to `.docx` (Windows + MS Word), then processes them.
- Can download URLs to `.mhtml` and process them.
- Inserts empty lines before and after image paragraphs.
- Preserves images while applying text corrections.
- Generates **two output formats automatically** from a single LLM pass:
  - `_corrected_inline.docx` — corrections shown inline with highlighting and deletion markers
  - `_corrected_track_changes.docx` — corrections shown via Word Track Changes with comments
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

1. Put input files in `input/` or in subdirectories (e.g., `input/1001/`, `input/6360/`, etc.).
2. Run interactive mode:

```shell
py .\process.py
```

3. Follow the interactive prompts:
   - Choose or create a course folder
   - View existing files in the selected folder
   - Optionally change the LLM model (keeps last used by default)
   - Optionally download URLs from `input/urls.txt`
   - Choose to process all files now or select specific files
4. Find outputs in `output/<course_folder>/`:
   - `<filename>_corrected_inline.docx`
   - `<filename>_corrected_track_changes.docx`

## Command-line mode

Process a DOCX:

```shell
py .\process.py --source-type docx --input "input\sample.docx"
```

Process an MHTML:

```shell
py .\process.py --source-type mhtml --input "input\sample.mhtml"
```

Process a PDF:

```shell
py .\process.py --source-type pdf --input "input\sample.pdf"
```

Download and process a URL:

```shell
py .\process.py --source-type url --input "https://example.com"
```

**Note:** Both `_corrected_inline.docx` and `_corrected_track_changes.docx` are always generated. The `-track` flag is accepted for backward compatibility but is no longer necessary.

## Folder layout

- `input/`: source files organized by course folder
  - `input/urls.txt` — list of URLs to download (optional)
  - `input/<course_folder>/` — DOCX, MHTML, PDF files to process
- `output/`: corrected files organized by course folder
  - `output/<course_folder>/<filename>_corrected_inline.docx` — inline corrections with highlighting
  - `output/<course_folder>/<filename>_corrected_track_changes.docx` — Track Changes format
  - `output/performance_log.csv` — performance metrics for all runs
- `process.py` — main entry point (interactive wizard or CLI mode)
- `document_processor.py` — builds correction plan and applies inline formatting
- `tracked_processor.py` — applies corrections via Word Track Changes
- `convert.py` — MHTML/PDF to DOCX conversion through Word automation
- `web_tools.py` — URL download to MHTML via Selenium

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

## Dual output modes

Both output formats are generated automatically from a **single LLM pass**, eliminating token waste:

- **Inline format** (`_corrected_inline.docx`):
  - Corrected text shown directly in the document
  - Additions highlighted in red bold
  - Deletions marked as `[-deleted_text-]` with strikethrough  
  - Explanatory comments inserted as Word comments
  - Useful for reviewing corrections in context

- **Track Changes format** (`_corrected_track_changes.docx`):
  - Corrections shown via Word's Track Changes feature
  - Character-level granularity (only changed characters marked)
  - Explanations attached as Word comments
  - Useful for formal review workflows where changes can be accepted/rejected individually

## Troubleshooting

- **No model available:**
    - Start Ollama and ensure a model is installed.
- **Interactive wizard shows no models:**
    - Ensure Ollama is running OR Azure providers are configured with environment variables.
- **MHTML/PDF conversion fails:**
    - Ensure Word is installed and `pywin32` is available.
    - Run `pip install pywin32` and restart Python.
- **Generated DOCX has no Track Changes output:**
    - Ensure `tracked_processor.py` is present.
    - If it's missing, only inline corrections will be generated.
- **Azure OpenAI initialization fails:**
    - Set `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_ENDPOINT`.
    - Ensure `Azure Deployment Name` matches your deployed model name in Azure OpenAI.
- **Azure AI Foundry initialization fails:**
    - Set `AZURE_AI_FOUNDRY_API_KEY` and `AZURE_AI_FOUNDRY_ENDPOINT`.
    - Ensure `Azure AI Foundry Model Name` matches your deployed model name in Azure AI Foundry.
- **Course folder prompt not appearing:**
    - The wizard always starts with course folder selection. Check there are no syntax errors in process.py.
- **File selection shows no processable files:**
    - Ensure `.docx`, `.mhtml`, or `.pdf` files exist in the selected course folder (not in subdirectories).
    - Exclude files with `_corrected` in the filename.

## Interactive wizard flow

The interactive wizard (`py process.py`) guides you through these steps:

1. **Course folder selection** — Choose an existing folder or create a new one (e.g., "1001", "6360")
2. **Show existing files** — Lists files already in the selected course folder
3. **Model selection (optional)** — Asks if you want to change the LLM model from the last used one
4. **Download URLs (optional)** — Asks if you want to download from `input/urls.txt`
5. **Processing strategy** — Asks whether to process all files now or choose specific files later
6. **File selection (if needed)** — Allows you to select specific files to process
7. **Processing** — Generates both inline and track-changes outputs
8. **Save preferences** — Stores your model choice for next run

## Prompt behavior

Prompts are loaded from `prompts.py` using `Active Prompt` in the configuration section. Two templates are provided:
- `default` — full spelling and grammar correction
- `grammar_only` — minimal corrections focused on grammar issues only
