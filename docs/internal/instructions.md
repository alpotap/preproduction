# Output Types and Behavior Instructions

Purpose: This file is the single place to describe and request output behavior changes.

How to use this file:
- Edit sections below to define what outputs you want.
- Add or update entries in the Change Requests section.
- In chat, you can simply say: "Apply instructions.md" and I will implement the changes from this file.

---

## Current Output Types (Implemented)

### 1) inline_docx
- Status: active
- Filename suffix: `_corrected_inline.docx`
- Description: Inline corrections in document text.
- Rendering behavior:
  - Added text appears highlighted/red.
  - Deleted text appears with deletion markers/strikethrough.
  - Explanations can be added as Word comments.
- Primary implementation files:
  - `document_processor.py`
  - `process.py`

### 2) track_changes_docx
- Status: active
- Filename suffix: `_corrected_track_changes.docx`
- Description: Uses Word Track Changes with comments.
- Rendering behavior:
  - Character-level revision tracking.
  - Explanations attached as comments.
- Primary implementation files:
  - `tracked_processor.py`
  - `process.py`

### 3) hybrid_docx
- Status: active
- Filename suffix: `_corrected_hybrid.docx`
- Description: Inline correction styling with Word comments for explanations.
- Primary implementation files:
  - `document_processor.py`
  - `process.py`

### 4) uncommented_docx
- Status: active
- Filename suffix: `_corrected_uncommented.docx`
- Description: Same inline correction style as inline output, but no reasons/comments and no simulated deletion markers.
- Primary implementation files:
  - `document_processor.py`
  - `process.py`

---

## Output Policy

- Default behavior: generate selected output types from one correction plan.
- Selection behavior:
  - Output types are multi-select in the wizard and persisted between runs.
  - The output-type menu is generated from the output registry, so newly added output types appear automatically once registered.
- Backward compatibility:
  - Legacy flags may be accepted but should not be required for normal usage.
- Output location:
  - Outputs are written under the configured output directory, typically by course subfolder.

## Prompt Policy

- Prompt templates are defined in `prompts.py`.
- Prompt selection is persisted between runs.
- Prompts may be sentence-level or paragraph-level, as long as they return the expected JSON correction structure.

---

## Change Requests (Edit This Section)

Use this format for any requested behavior or new output type.

### Request Template
- Request ID:
- Priority: high | medium | low
- Type: modify_existing | add_new_output_type | remove_output_type | naming_change | performance
- Target output type:
- Requested change:
- Acceptance criteria:
- Sample input path(s):
- Expected output path(s):
- Notes:

### Active Requests

#### Request ID: EXAMPLE-001
- Priority: medium
- Type: add_new_output_type
- Target output type: hybrid_docx
- Requested change: Add a third output format that combines inline color changes with Word comments.
- Acceptance criteria:
  - New file produced with suffix `_corrected_hybrid.docx`.
  - Existing inline and track-changes outputs remain unchanged.
- Sample input path(s): `input/6360/sample.docx`
- Expected output path(s): `output/6360/sample_corrected_hybrid.docx`
- Notes: Keep runtime increase under 20%.

---

## Output Type Registry (Planned + Implemented)

Use one block per output type.

### output_type: <name>
- status: active | planned | deprecated
- suffix: <filename suffix>
- source_types_supported: docx | mhtml | pdf | url
- needs_comments: true | false
- needs_track_changes: true | false
- description: <short purpose>
- compatibility_notes: <optional>

---

## Rules for Future Edits

- Do not remove existing output types unless explicitly requested.
- Preserve existing filename conventions unless a naming_change request exists.
- Keep changes backward compatible where possible.
- If a request affects performance, log before/after impact.

---

## Implementation Notes (For Assistant)

When applying requests from this file, prioritize updates in:
- `process.py` (thin CLI entry point)
- `engine.py` (shared orchestration and processing engine for CLI/API use)
- `wizard_ui.py` (interactive terminal prompts and CLI-only flow)
- `local_web.py` (localhost web API and single-page app host)
- `web_jobs.py` (background queue and web execution status/log handling)
- `docs/api_contract.md` (stable endpoint contract for web integrations)
- `providers.py` (provider normalization/settings/client creation)
- `output_types.py` (output type registry and persistence helpers)
- `document_processor.py` (inline/hybrid rendering)
- `tracked_processor.py` (track changes rendering)
- `readme.md` (user-facing behavior summary)

Web queue behavior policy:
- Job history should persist in `output/web_job_history.json` for restart continuity.
- Queue/UI should support cancel and retry actions.
- Running cancellation is best-effort and should be cooperative at safe checkpoints.

If a request is ambiguous, implement the safest minimal version and document assumptions in the commit summary.
