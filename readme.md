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
LLM Provider: github
LLM Model: gpt-4o-mini
LLM Temperature: 0.1
LLM Max Tokens: 8000

## Model providers

- `ollama`: local model endpoint (`http://localhost:11434/v1`)
- `github`: GitHub Models endpoint (requires `GITHUB_TOKEN` or `GH_TOKEN`)

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
- GitHub model fails:
    - Set `GITHUB_TOKEN` or `GH_TOKEN` in your environment.

## Prompt behavior

Prompts are loaded from `prompts.py` using `Active Prompt` in the configuration section above.
