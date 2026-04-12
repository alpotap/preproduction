# Document Correction Toolkit

This project corrects Word documents and web content while preserving structure, batching LLM requests efficiently, and generating selectable review outputs from a shared correction plan.

## What it does

- Processes `.docx` files directly.
- Converts `.mhtml` files to `.docx` (Windows + MS Word), then processes them.
- Converts `.pdf` files to `.docx` (Windows + MS Word), then processes them.
- Can download URLs to `.mhtml` and process them.
- Inserts empty lines before and after image paragraphs.
- Preserves images while applying text corrections.
- Generates one or more selectable output formats from a single LLM pass:
  - `_corrected_inline.docx` — inline corrections with explanation text and deletion markers
  - `_corrected_uncommented.docx` — inline corrections without explanation text or deletion markers
  - `_corrected_track_changes.docx` — Word Track Changes with comments
  - `_corrected_hybrid.docx` — inline corrections with real Word comments
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
  - Optionally change the selected output types (multi-select, remembered between runs)
   - Optionally download URLs from `input/urls.txt`
   - Choose to process all files now or select specific files
4. Find outputs in `output/<course_folder>/`:
   - `<filename>_corrected_inline.docx`
  - `<filename>_corrected_uncommented.docx`
   - `<filename>_corrected_track_changes.docx`
  - `<filename>_corrected_hybrid.docx`

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

**Note:** The generated output files depend on your saved `Output Types` selection. The `-track` flag is accepted for backward compatibility but is no longer necessary.

## Folder layout

- `input/`: source files organized by course folder
  - `input/urls.txt` — list of URLs to download (optional)
  - `input/<course_folder>/` — DOCX, MHTML, PDF files to process
- `output/`: corrected files organized by course folder
  - `output/<course_folder>/<filename>_corrected_inline.docx` — inline corrections with highlighting
  - `output/<course_folder>/<filename>_corrected_uncommented.docx` — inline corrections without reasons or deletion markers
  - `output/<course_folder>/<filename>_corrected_track_changes.docx` — Track Changes format
  - `output/<course_folder>/<filename>_corrected_hybrid.docx` — inline corrections plus Word comments
  - `output/performance_log.csv` — performance metrics for all runs
- `process.py` — main entry point (interactive wizard or CLI mode)
- `document_processor.py` — builds correction plan and applies inline formatting
- `tracked_processor.py` — applies corrections via Word Track Changes
- `convert.py` — MHTML/PDF to DOCX conversion through Word automation
- `web_tools.py` — URL download to MHTML via Selenium

## Output Change Workflow

To request output behavior changes or new output types without re-explaining details in chat, use:

- `instructions.md` — source of truth for output types, policies, and change requests

Update `instructions.md`, then ask to "apply instructions.md".

## Configuration

This section is read by the tool at runtime. Keep keys and formatting as `Key: value`.

Language: en-US
Input Directory: input
Output Directory: output
Highlight Corrections: true
Add Comments: true
Active Prompt: default
LLM Provider: ollama
LLM Model: gpt-oss:120b-cloud
LM Studio Base URL: http://127.0.0.1:1234/v1
LM Studio Model Name:
Azure API Version: 2025-03-01-preview
Azure Deployment Name: GPT 40 mini (low quality but very fast)
Azure AI Foundry Model Name: gpt-oss-120b
LLM Temperature: 0.1
LLM Max Tokens: 8000
Output Types: inline, uncommented, track_changes, hybrid

## Model providers

- `ollama`: local model endpoint (`http://localhost:11434/v1`)
- `lm_studio`: local LM Studio OpenAI-compatible server (`http://127.0.0.1:1234/v1`)
- `azure_openai`: Azure OpenAI endpoint (requires Azure environment variables)
- `azure_ai_foundry`: Azure AI Foundry endpoint (requires Azure AI Foundry environment variables, no API version required)

## Environment Variables by Provider

### Ollama
No environment variables needed. Ollama uses local endpoint `http://localhost:11434/v1`.

### LM Studio

- Start LM Studio local server and load a model.
- By default, the tool uses `LM Studio Base URL` from configuration (`http://127.0.0.1:1234/v1`).
- Optional environment variable:
  - `LM_STUDIO_BASE_URL` — overrides the configuration base URL.

The wizard will check if LM Studio is reachable, list available model IDs from the server, and let you choose one.

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

Performance logging (`output/performance_log.csv`) includes both `input_tokens` (sent to model) and `tokens_generated` (received from model).

Raw LLM responses are also tracked in `output/llm_raw_output.log`. The file is automatically trimmed to the last 2000 lines so it can be tailed during long runs.

## Notes on image handling

- Blank lines are inserted before and after image paragraphs before AI processing.
- Paragraphs that include images are updated with image-preserving logic.
- This prevents inline images from being removed during correction.

## Output modes

Selected output formats are generated from a **single LLM pass**, eliminating token waste:

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

- **Uncommented inline format** (`_corrected_uncommented.docx`):
  - Same inline correction styling as inline format
  - No reason/comments are embedded in the document text
  - Deleted text is removed cleanly without `[-deleted_text-]` placeholders
  - Useful when you want visual correction marks without explanatory notes

Output generation is selectable in the wizard (multi-select), and your selection is remembered between runs.

## Troubleshooting

- **No model available:**
  - Start Ollama or LM Studio and ensure a model is loaded.
- **Interactive wizard shows no models:**
  - Ensure Ollama or LM Studio server is running OR Azure providers are configured with environment variables.
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

1. **Level A task menu** — Choose processing, download-and-process, model selection, consistency analysis, or output type selection
2. **Output type selection (optional)** — Multi-select output types and return to the Level A menu
3. **Course folder selection** — Choose an existing folder or create a new one (for example, `1001`, `6360`)
4. **Show existing files** — Lists files already in the selected course folder
5. **Prompt selection** — Choose the prompt template for this run
6. **Download URLs (optional)** — Download from `input/urls.txt` into the selected course folder
7. **File selection** — Select the files to process
8. **Processing** — Generates the selected output types from one correction plan
9. **Save preferences** — Stores model, prompt, and output type choices for next run

## Prompt behavior

Prompts are loaded from `prompts.py` using `Active Prompt` in the configuration section. Current prompt templates include:
- `default` — full copy edit for spelling, grammar, punctuation, voice, and clarity
- `grammar_only` — spelling, grammar, and punctuation only
- `paragraph_rewrite` — analyze text and rewrite full paragraphs when broader changes are justified
- `redundancy_analysis` — identify repeated or redundant content
- `terminology_consistency` — align inconsistent term usage to an existing form
- `structural_integrity` — validate heading hierarchy and section organization
- `cross_reference_validation` — validate internal references and citations
- `audience_tone_alignment` — identify tone and audience mismatches
