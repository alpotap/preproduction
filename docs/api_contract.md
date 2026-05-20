# Local Web API Contract

Version: v1
Base URL: http://127.0.0.1:8000

This contract defines stable endpoints for the localhost single-page web app and any future separate frontend.

When hosted as the Windows background service, the endpoint surface is unchanged. Only the hosting mode differs.

The effective input and output roots behind these endpoints come from `paths.json`. The API does not expose any endpoint to edit those root paths.

## Conventions

- Content type: JSON unless endpoint returns file content.
- Time format: ISO-8601 strings.
- Job status values: queued, running, completed, failed, canceled.
- Upload limit: 20 MB per file.

## Capability and Metadata Endpoints

### GET /api/capabilities

Returns prompts, output types, providers, and effective defaults.

Response fields:
- config.llmProvider
- config.llmModel
- config.activePrompt
- config.outputTypes
- prompts[] with key, name, version, summary, details, category
- promptCategories[] including `copy_editing`, `document_analysis`, `multi_document_analysis`, `staging`
- outputTypes[] with key, label, suffix
- providers[] with key, label (only providers with configured/available model options)

Notes:
- Azure AI Foundry can expose multiple provider keys when vendor categories are configured, for example `azure_ai_foundry` and `foundry_vendor_openai`.
- Prompt list behavior: only the latest production version in each lineage is returned for user selection, while all staging prompts are returned under the `staging` category.
- Prompt catalogs are edited in `*.prompt.md`, and matching `*.json` artifacts are generated automatically on startup/reload.
- Prompt `name` values include version in display text for user-facing selection surfaces.
- Staging prompt markdown filenames are normalized with version suffixes during reload.
- Correction sanitation in processing paths blocks duplicate terminal punctuation artifacts (for example `..`) when list-item period fixes are augmented and applied.
- Correction post-processing mode is controlled by `AI Only Corrections` in `readme.md` runtime configuration and is shared across CLI and web runs.
- Objective punctuation guardrails apply in both modes and drop invalid terminal appends such as `?.`, `!.`, and `:.`.
- Empty correction responses on non-trivial inputs can trigger one low-temperature retry when `Retry On Empty Corrections: true` is set in `readme.md`.

### GET /api/models?provider=<provider_key>

Returns model options for a provider.

Response fields:
- models[] where each item is one of:
  - string model ID (Ollama/LM Studio)
  - object `{ value, label, model_name, profile, display_name, vendor, provider_key }` (Azure AI Foundry)

### POST /api/preferences

Persists shared default selections used by both CLI and web sessions.

Request body:
- promptKey: string | null
- outputTypes: string[] | null
- provider: string | null
- model: string | null

Response fields:
- status
- saved[]

Notes:
- Values are persisted to the runtime configuration in `readme.md`.
- Azure AI Foundry endpoint/auth settings remain environment-driven; selected model defaults are persisted.

### GET /api/provider-status

Returns provider connectivity/config snapshots.

Notes:
- For `azureAiFoundry`, endpoint/model settings are environment-only.
- Recommended setup on Windows uses `python setup_foundry_env.py`, which provides list/add/edit/remove/test actions and writes the required environment variables to both USER and MACHINE scopes by default.
- Run setup from an elevated session, then restart the service/app so all users see the same profile set.
- Single-profile mode uses `AZURE_AI_FOUNDRY_API_KEY`, `AZURE_AI_FOUNDRY_ENDPOINT`, `AZURE_AI_FOUNDRY_API_VERSION`, `AZURE_AI_FOUNDRY_MODEL_NAME`.
- Multi-profile mode uses `AZURE_AI_FOUNDRY_PROFILE_IDS` and per-profile variables (`AZURE_AI_FOUNDRY_<PROFILE>_API_KEY`, `_ENDPOINT`, `_API_VERSION`, `_MODEL_NAME`, `_DISPLAY_NAME`, `_VENDOR`).

## Folder and File Endpoints

### GET /api/folders?scope=input|output

Lists folders under input/output root.

Response fields:
- folders[]

### POST /api/folders

Creates input folder.

Request body:
- name (string)

Response fields:
- folder

### POST /api/uploads?folder=<name>

Uploads one or more files to input folder.

Multipart field:
- files[]

Response fields:
- saved[] with name, size
- rejected[] with name, reason

### GET /api/files?scope=input|output&folder=<optional>

Lists files recursively with metadata.

Notes:
- For `scope=output`, internal sidecar files (for example `summary_report_state.json`) are intentionally omitted from list results.

Response fields:
- files[] with:
  - name
  - relativePath
  - folder
  - sizeBytes
  - modifiedAt
  - downloadUrl
  - extension

### GET /api/download/{scope}/{relative_path}

Downloads a file.

### GET /api/download-zip?scope=input|output&folder=<name>

Generates a zip archive from the selected folder and saves it under the output root.

Response fields:
- status
- scope
- sourceFolder
- outputFolder
- outputFile
- outputRelativePath

### GET /api/processable-files?folder=<name>

Lists processable files (`.docx`, `.mhtml`, `.pdf`) for one input folder.

Response fields:
- files[] with:
  - name
  - extension
  - sizeBytes
  - modifiedAt

## Job Endpoints

### POST /api/jobs

Enqueues a new job.

Request body:
- taskType: process | download_process | consistency
- folder: string
- promptKey: string | null
- outputTypes: string[] | null
- provider: string | null
- model: string | null
- urls: string | null
- selectedFiles: string[] | null

Response fields:
- job (job record)

Processing side effects:
- For process/download_process jobs, the service also updates `output/<folder>/summary_report_state.json` and `output/<folder>/summary_report.docx` from execution statistics.
- Job submission also persists selected provider/model/prompt/output types as shared defaults for future CLI/web sessions.
- For download_process jobs, processing is limited to newly added files for that run (for Wizard usage: files created by URL downloads); pre-existing processable files in the folder are excluded unless explicitly selected via API.

In all path examples above, `input` and `output` refer to the roots defined in `paths.json`.

### GET /api/jobs

Returns latest-first job list.

Response fields:
- jobs[]

Each job record includes:
- processedFiles
- downloadedUrls
- correctionCount (total corrections across all files in the job)
- totalInputTokens
- totalTokensGenerated
- totalTokens (input + generated)
- outputCount (legacy total files currently present in output folder)

### POST /api/jobs/{job_id}/cancel

Cancel behavior:
- Queued: canceled immediately.
- Running: marks cancelRequested=true and attempts cooperative cancel at safe checkpoints.
- Other statuses: 400.

Response fields:
- job (updated job record)

### POST /api/jobs/{job_id}/retry

Retry behavior:
- Allowed from completed, failed, or canceled.
- Creates a new queued job with parentJobId and retries incremented.

Response fields:
- job (new job record)

### GET /api/status

Returns active run and queue summary.

Response fields:
- currentRun
- queueLength
- queuedJobs
- totalJobs

### GET /api/run-state

Alias of status endpoint.

## Log Endpoints

### GET /api/logs/{kind}?lines=1..5000

Kind values:
- execution
- performance
- raw

Response fields:
- content

Raw log behavior:
- `kind=raw` returns content from `output/llm_raw_output.log`.
- Each raw entry includes `--- INPUT ---` and `--- OUTPUT ---` blocks.
- Each raw entry includes `input_preview` and `output_preview` lines near the end of the entry for tail readability.
- The raw log file is capped at 10 MB and older content is trimmed automatically.

## Remote Debug Endpoints

These endpoints support collecting diagnostics from a separate remote host and sending them back to this machine for analysis.

### POST /api/debug/upload

Uploads a remote debug bundle as multipart form data.

Multipart field:
- file

Response fields:
- status
- filename
- size_bytes
- stored_at

### GET /api/debug/bundles?limit=1..100

Lists recently received debug bundles.

Response fields:
- bundles[] with:
  - filename
  - timestamp
  - job_id
  - task_type
  - status
  - size_bytes
  - download_url

### GET /api/debug/bundles/{bundle_filename}

Downloads one stored debug bundle.

### POST /api/debug/analyze

Accepts one uploaded bundle and returns a quick diagnostic summary.

Multipart field:
- file

Response fields:
- timestamp
- job_id
- task_type
- status
- issues[]
- recommendations[]
- system_health
- error_traceback (when present)
- recent_messages (when present)
- performance (when present)

### GET /api/debug/health-check

Returns a lightweight health snapshot so a remote host can verify connectivity before sending larger bundles.

Response fields:
- status
- timestamp
- hostname
- platform
- python_version
- cpu_usage_percent
- memory_usage_percent
- disk_usage_percent
- api_version

### POST /api/debug/test-error

Development-only endpoint that creates a synthetic error and writes a local debug bundle to validate the capture pipeline.

## Service Endpoint

### GET /health

Response fields:
- ok: true

## Job Record Schema

Job response object fields:
- id
- taskType
- folder
- status
- createdAt
- startedAt
- finishedAt
- currentMessage
- error
- processedFiles
- downloadedUrls
- outputCount
- retries
- parentJobId
- cancelRequested
- options

## Persistence and Restart

Job history is persisted to output/web_job_history.json.

On service restart:
- completed, failed, canceled jobs remain as historical records
- queued and running jobs are restored as queued with message "Requeued after service restart"
