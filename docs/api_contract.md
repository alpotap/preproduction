# Local Web API Contract

Version: v1
Base URL: http://127.0.0.1:8000

This contract defines stable endpoints for the localhost single-page web app and any future separate frontend.

When hosted as the Windows background service, the endpoint surface is unchanged. Only the hosting mode differs.

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
- prompts[] with key, name, summary
- outputTypes[] with key, label, suffix
- providers[] with key, label

### GET /api/models?provider=<provider_key>

Returns model IDs for a provider.

Response fields:
- models[]

### GET /api/provider-status

Returns provider connectivity/config snapshots.

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

### GET /api/jobs

Returns latest-first job list.

Response fields:
- jobs[]

### POST /api/jobs/{job_id}/cancel

Cancel behavior:
- queued: canceled immediately
- running: marks cancelRequested=true and attempts cooperative cancel at safe checkpoints
- other statuses: 400

Response fields:
- job (updated job record)

### POST /api/jobs/{job_id}/retry

Retry behavior:
- allowed from completed, failed, or canceled
- creates a new queued job with parentJobId and retries incremented

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
