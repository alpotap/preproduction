# Repository Engineering Rules

These rules are permanent and apply to all future code changes.

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
