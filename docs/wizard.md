# Wizard and CLI Guide

→ [Back to readme.md](../readme.md)

## Quick start

```shell
py .\process.py
```

The interactive wizard runs in the terminal and guides you through folder selection, uploading, and job processing. No flags are required for normal use.

Input and output roots come from `paths.json`. The wizard can create subfolders under the configured input root, but it cannot change the root paths themselves.

For unattended web hosting on Windows, use the separate service installer described in [webapp.md](webapp.md#windows-service-deployment).

## Interactive wizard flow

1. **Task menu** — Choose one of:
   - Process existing files
   - Download URLs and process
   - Change LLM model
   - Run consistency analysis
   - Select output types

2. **Output type selection** — Multi-select the formats to generate. Your selection is remembered between runs.

3. **Course folder selection** — Choose an existing input subfolder or create a new one (e.g. `1001`, `6360`).

4. **Show existing files** — Lists files already in the selected course folder.

5. **Prompt selection** — Choose the prompt template to use.

6. **Download URLs (optional)** — Downloads from `input/urls.txt` into the selected course folder.

7. **File selection** — Choose which files to process (all or individual).

8. **Processing** — Sends each file through the LLM and generates selected output formats from one correction plan.

9. **Summary report update (automatic)** — After every run, the tool updates:
   - `output/<folder>/summary_report_state.json` (historical execution stats)
   - `output/<folder>/summary_report.docx` (readable report with run and category totals)

10. **Save preferences** — Prompt and output type choices are stored for the next session. Azure AI Foundry profile/model values are read from environment variables and are not stored in `readme.md`.

11. **Foundry profile selection (when configured)** — If multiple Azure AI Foundry profiles are configured through environment variables, the model list includes profile-qualified entries such as `gpt-4o-mini [primary]`.

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

Output formats generated depend on the saved Output Types selection.

For URL processing and wizard folder selection, the base input/output roots are taken from `paths.json`.

The summary report artifacts are always generated automatically and are not part of Output Types selection.

## Prompts

Prompts are loaded from `prompts.py`. The active prompt is set by `Active Prompt:` in `readme.md` configuration or overridden per-run in the wizard.

| Key | Description |
|---|---|
| `default` | Full copy edit: spelling, grammar, punctuation, voice, clarity |
| `grammar_only` | Spelling, grammar, and punctuation only |
| `paragraph_rewrite` | Rewrite full paragraphs where broader changes are justified |
| `redundancy_analysis` | Identify repeated or redundant content |
| `terminology_consistency` | Align inconsistent term usage to an existing form |
| `structural_integrity` | Validate heading hierarchy and section organization |
| `cross_reference_validation` | Validate internal references and citations |
| `audience_tone_alignment` | Identify tone and audience mismatches |

## Output formats

All selected formats are generated from a **single LLM pass** — no extra API calls per additional format.

### `_corrected_inline.docx`
- Added text: red bold
- Deleted text: `[-deleted_text-]` strikethrough
- Explanations: Word comments
- Best for reviewing corrections in context

### `_corrected_track_changes.docx`
- Corrections shown via Word Track Changes
- Character-level granularity
- Explanations as Word comments
- Best for formal review workflows (accept/reject individual changes)

### `_corrected_hybrid.docx`
- Inline correction styling + real Word comments for explanations
- Combines visual clarity of inline with comment-panel navigation

### `_corrected_uncommented.docx`
- Same inline correction styling as inline format
- No explanatory comments or deletion placeholders
- Deletions removed cleanly
- Best when you want visual correction marks without notes

## CLI troubleshooting

- **No processable files found** — Ensure `.docx`, `.mhtml`, or `.pdf` files exist directly in the selected folder (not in subdirectories). Files with `_corrected` in the name are excluded.
- **MHTML files remain after a web Download + Process job** — Update to the latest code and rerun. New web jobs clean up source `.mhtml` files after successful conversion.
- **MHTML/PDF conversion fails** — Requires Microsoft Word and `pywin32`. Run `pip install pywin32` and ensure Word is installed.
- **No model available** — Check that your LLM provider (Ollama, LM Studio, or Azure AI Foundry) is reachable and configured. For Azure AI Foundry, run `python setup_foundry_env.py` and re-open the app. See [configuration.md](configuration.md).
- **Azure AI Foundry with gpt-4o-mini fails** — Use endpoint root `https://<resource>.cognitiveservices.azure.com/` (not `/openai/v1`) and set `AZURE_AI_FOUNDRY_API_VERSION` (for example `2025-01-01-preview`).
- **Wizard does not start** — Check `process.py` for syntax errors.
- **Web UI should run after reboot without a terminal** — Install the Windows service with `Register-WebService.ps1 -Action Install` as described in [webapp.md](webapp.md#windows-service-deployment).

## Running on a remote server

The CLI wizard is still local and interactive, but the processing stack can run on another host. For remote execution, wrap the processing entrypoint with the debug helper so failures can be sent back here as structured bundles.

See [remote_debugging.md](remote_debugging.md) for the collector, upload endpoint, and analysis workflow.
