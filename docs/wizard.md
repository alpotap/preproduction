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
   - Use prompt selection for consistency analysis workflows
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

10. **Save preferences** — Provider, model, prompt, and output type choices are stored for the next session and shared with the web UI for all users on the same host.

## Hidden Whitespace Handling

The tool automatically detects and normalizes invisible Unicode whitespace characters (non-breaking spaces, zero-width characters, etc.) in source documents before analysis. This prevents false-positive corrections like "Missing space before 'dialog'" when the spacing is visually correct but hidden characters are present. Normalized text is used during LLM analysis, and corrections caused purely by invisible whitespace are dropped automatically.
Correction sanitation also blocks duplicate terminal punctuation artifacts during list-item punctuation fixes so outputs do not gain trailing `..`.

11. **Foundry profile and vendor selection (when configured)** — If multiple Azure AI Foundry profiles are configured through environment variables, the model list includes profile-qualified display names such as `My Editing Model [primary]` and groups provider options by configured vendor category.

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

Prompts are loaded from filesystem catalogs under `prompts/prod` and `prompts/staging`. Human-editable prompt files use `.prompt.md`, and startup automatically regenerates matching `.json` files from markdown. The active prompt is set by `Active Prompt:` in `readme.md` configuration or overridden per-run in the wizard.

By default, correction output uses model-provided corrections only (`AI Only Corrections: true` in `readme.md` runtime configuration), which avoids local augmentation rules and helps isolate prompt/model behavior during validation.
Even in AI-only mode, objective output guardrails remain enabled and remove invalid terminal punctuation appends such as `?.`, `!.`, and `:.`.
When `Retry On Empty Corrections: true`, non-trivial inputs that return `[]` are retried once at temperature `0.0`.

Prompt catalog behavior:

- Every prompt has a `version` field (current baseline `1.0`).
- A `staging` category is loaded from `prompts/staging` for test runs.
- `prompt_category` controls grouping/selection only. Input handling behavior is not inferred from category; behavior-specific controls use prompt metadata such as `output_mode`.
- Promotion is manual by copying a prompt file from `prompts/staging` into `prompts/prod`.
- If multiple production versions exist for one prompt lineage, only the latest production version is shown in selection lists.
- Markdown files are the source of truth for editing.
- Staging markdown prompt filenames are normalized to include version suffixes (for example, `default_v1_1.prompt.md`).
- Prompt names displayed in wizard selections include the version.

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
- Best for reviewing corrections in context.

### `_corrected_track_changes.docx`
- Corrections shown via Word Track Changes
- Character-level granularity
- Explanations as Word comments
- Best for formal review workflows (accept/reject individual changes).

### `_corrected_hybrid.docx`
- Inline correction styling + real Word comments for explanations
- Combines visual clarity of inline with comment-panel navigation

### `_corrected_uncommented.docx`
- Same inline correction styling as inline format
- No explanatory comments or deletion placeholders
- Deletions removed cleanly
- Best when you want visual correction marks without notes.

## CLI troubleshooting

- **No processable files found** — Ensure `.docx`, `.mhtml`, or `.pdf` files exist directly in the selected folder (not in subdirectories). Files with `_corrected` in the name are excluded.
- **MHTML files remain after a web Download + Process job** — Update to the latest code and rerun. New web jobs clean up source `.mhtml` files after successful conversion.
- **MHTML/PDF conversion fails** — Requires Microsoft Word and `pywin32`. Run `pip install pywin32` and ensure Word is installed.
- **No model available** — Check that your LLM provider (Ollama, LM Studio, or Azure AI Foundry) is reachable and configured. Re-run `python setup_foundry_env.py` from an elevated session so USER and MACHINE scopes are synchronized, then re-open the app. Use `--scope user` only for local single-user scenarios. See [configuration.md](configuration.md).
- **Need to inspect exact model I/O** — Check `output/llm_raw_output.log`. Each entry includes `--- INPUT ---` and `--- OUTPUT ---` blocks. The file is capped at 10 MB and auto-trimmed from the oldest entries.
- **Azure AI Foundry with gpt-4o-mini fails** — Use endpoint root `https://<resource>.cognitiveservices.azure.com/` (not `/openai/v1`) and set `AZURE_AI_FOUNDRY_API_VERSION` (for example `2025-01-01-preview`).
- **Wizard does not start** — Check `process.py` for syntax errors.
- **Web UI should run after reboot without a terminal** — Install the Windows service with `Register-WebService.ps1 -Action Install` as described in [webapp.md](webapp.md#windows-service-deployment).

## Running on a remote server

The CLI wizard is still local and interactive, but the processing stack can run on another host. For remote execution, wrap the processing entrypoint with the debug helper so failures can be sent back here as structured bundles.

See [remote_debugging.md](remote_debugging.md) for the collector, upload endpoint, and analysis workflow.
