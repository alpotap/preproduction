# Repository Engineering Rules

These rules are permanent and apply to all future code changes.

## Fast Start For Agents

- Use Python entrypoints exactly as documented in [readme.md](../readme.md).
- CLI run: `py .\\process.py`.
- Web run: `py .\\local_web.py` (or `run_web.bat` on Windows).
- Install dependencies: `py -m pip install -r requirements.txt`.
- Test suite: `python -m pytest tests -q`.
- Focused retry test: `python -m pytest tests/test_empty_result_retry.py -q`.

## Architecture Boundaries

- Keep `process.py` and `local_web.py` thin; put reusable behavior in `toolkit/`.
- Use `toolkit/engine.py` for orchestration and runtime config hydration.
- Use `toolkit/providers.py` for provider/model resolution logic.
- Use `toolkit/llm_service.py` for LLM calls, parsing, retry, and token accounting.
- Use `toolkit/document_processor.py` and `toolkit/tracked_processor.py` for output rendering paths.
- Treat `paths.json` as the source of truth for input/output roots.
- Treat `readme.md` Runtime Configuration as the source of truth for persisted runtime defaults.

## High-Risk Pitfalls

- Preserve backward compatibility for CLI and web flows unless a breaking change is explicitly requested.
- Do not introduce provider/model persistence outside existing runtime config and environment-variable paths.
- Keep Azure AI Foundry credentials and endpoint configuration environment-driven; never hardcode secrets.
- Keep prompt behavior and correction behavior synchronized with tests in `tests/` when changing retry or sanitation logic.
- Keep API and UI contracts synchronized by updating [docs/api_contract.md](../docs/api_contract.md) with behavior changes.

## Link-First Documentation Policy

- Link to existing docs for details instead of duplicating long operational guidance.
- Configuration and provider setup: [docs/configuration.md](../docs/configuration.md).
- CLI workflow and troubleshooting: [docs/wizard.md](../docs/wizard.md).
- Web workflow and service deployment: [docs/webapp.md](../docs/webapp.md).
- API payloads and endpoint contracts: [docs/api_contract.md](../docs/api_contract.md).
- Remote diagnostics: [docs/remote_debugging.md](../docs/remote_debugging.md).

## Code Hygiene

- Remove dead code when touching related modules.
- Avoid duplicate or redundant implementations.
- Prefer one canonical implementation per function or workflow.
- Keep imports and helper utilities minimal and scoped to use.

## Separation of Responsibilities

- Python files contain executable logic only.
- Markdown files contain documentation and operational guidance only.
- Do not embed business logic in markdown.
- Keep CLI/web entrypoints thin; put shared logic in toolkit modules.

## Documentation Maintenance

- Update affected markdown docs whenever behavior, APIs, configuration, or workflows change.
- Keep docs synchronized with runtime behavior in the same change set.
- At minimum, review and update:
  - readme.md
  - docs/wizard.md
  - docs/webapp.md
  - docs/configuration.md
  - docs/api_contract.md

## Change Quality

- Preserve backward compatibility unless a breaking change is explicitly requested.
- Prefer small, focused refactors with explicit cleanup notes.
- After edits, run at least a smoke validation for the touched flow (CLI or web).

## Changelog Maintenance

- After every `git push`, write a short entry in `CHANGELOG.md` summarizing what changed.
- Place the entry under a new dated section (e.g., `## [YYYY-MM-DD]`) using the current date.
- Use compact bullet points: one line per notable change, grouped under `Added`, `Changed`, or `Fixed` as appropriate.
- If the push contains only minor edits or no user-facing changes, a single sentence under the date is sufficient.

## List Punctuation (Microsoft Style Guide)

- **Bulleted lists:** End each item with a period if the item is a complete sentence or clause.
- **Numbered lists:** Always end items with a period.
- **Consistency:** Within a single list, either all items have terminal punctuation or none do. If any item is a complete sentence, all items in that list must have periods.
- **Item labels and fragments:** Simple labels, category names, or field names without predicates do not require periods (e.g., "Language", "Ollama", "Output Types").
