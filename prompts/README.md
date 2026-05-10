# Prompt Catalog Format

Prompt catalogs are loaded from:

- `prompts/prod`
- `prompts/staging`

Preferred format is `*.prompt.md` because it is easier to read and edit.

Markdown files are the source of truth. The application regenerates matching `.json` prompt files automatically on startup/reload in `prompts/generated/`.

## Markdown Prompt File Format

Use this structure:

```md
---
name: Full Copy Edit
abbr: FCE
prompt_category: copy_editing
summary: Checks spelling, grammar, punctuation, voice, and clarity while preserving meaning.
max_input_words: 500
version: 1.0
output_mode: corrections
max_tokens_override: 2000
---
You are a professional copy editor...

Text: {text}
```

Metadata notes:

- Required: `template` body (the text after the closing `---`).
- Recommended: `name`, `abbr`, `prompt_category`, `summary`, `max_input_words`, `version`.
- Optional: `output_mode`, `max_tokens_override`.

Runtime notes:

- Prompt key is derived from file name:
  - `default.prompt.md` -> key `default`
  - `default_v1_1.prompt.md` -> key `default_v1_1` (version is inferred as `1.1`)
- Staging prompts are loaded from the staging folder and exposed under staging runtime keys.
- Runtime JSON artifacts are generated from markdown in `prompts/generated/prod` and `prompts/generated/staging`.
- Staging markdown filenames are auto-normalized to include version suffixes (for example, `default_v1_1.prompt.md`).
- Prompt display names shown in CLI/web include version in the name.

## Conversion Utility

Convert existing JSON prompts to markdown:

```shell
py -m toolkit.prompt_catalog_converter
```

Convert and remove source JSON files:

```shell
py -m toolkit.prompt_catalog_converter --remove-json
```
