# Web UI Guide

→ [Back to readme.md](../readme.md)

## Starting the web server

```shell
py .\local_web.py
```

Or use the batch file:

```shell
.\run_web.bat
```

Then open **http://127.0.0.1:8000** in any browser.

The web app reads its input and output roots from `paths.json`. Those paths are shared with the CLI and are not editable from the web UI.

## Windows service deployment

If this machine should host the web UI continuously, register it as a Windows service so users do not need to start `local_web.py` manually.

Install from an elevated PowerShell session:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\Register-WebService.ps1 -Action Install -InstallRequirements
```

What the installer does:

1. Writes `output/web_service_config.json` with the host and port.
2. Installs the `DocumentCorrectionToolkitWeb` Windows service.
3. Sets the service to start automatically at boot.
4. Configures restart-on-failure recovery.
5. Starts the service immediately.

Useful variants:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\Register-WebService.ps1 -Action Install -Host 0.0.0.0 -Port 8000 -OpenFirewall
PowerShell -ExecutionPolicy Bypass -File .\Register-WebService.ps1 -Action Restart -Host 127.0.0.1 -Port 8010
PowerShell -ExecutionPolicy Bypass -File .\Register-WebService.ps1 -Action Status
PowerShell -ExecutionPolicy Bypass -File .\Register-WebService.ps1 -Action Uninstall
```

Service logs are written to:

- `output/web_service.log`
- `output/web_service_error.log`

The service host is implemented in `windows_web_service.py` and launches the same FastAPI app as the interactive `local_web.py` entrypoint.

If `paths.json` points `output_dir` somewhere else, the service config, logs, job history, and debug bundles are written under that configured output root instead of the repository-local `output` folder.

## Restarting the web server

The server has no live-reload. To restart after code or config changes:

1. Find the terminal or process running `local_web.py`.
2. Press `Ctrl+C` to stop it.
3. Run `py .\local_web.py` again (or `.\run_web.bat`).

If you started it with `run_web.bat` and the window is closed, just run it again — the job history file (`output/web_job_history.json`) will restore previously queued jobs automatically.

If you installed the Windows service, use `Register-WebService.ps1 -Action Restart` instead of restarting a terminal window.

**If a port conflict occurs:**

```powershell
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

Then restart normally.

## Tabs

### Wizard

Step-by-step job submission:

1. Select task type (process, download+process).
	- Consistency analysis is selected through Prompt selection (for example from Document Analysis prompts), not as a separate task type.
2. Choose or create an input folder.
	- Task, input folder, and new-folder creation controls are aligned in one row on desktop and stack automatically on narrow screens.
	- The Files To Process list shows each eligible file in a single full-width row with file size and last processed timestamp.
	- In **Process existing files**, you can drag and drop files directly into the Files To Process section to upload them into the selected input folder.
	- The Files To Process section shows an inline tip for drag-and-drop upload.
3. Paste URLs to download (for download tasks).
	- URL controls are shown only when task type is **Download and process**.
	- In **Download and process**, the job processes newly downloaded files from the provided URLs and ignores pre-existing files in the folder.
4. Choose prompt, provider, model, and output types.
	- Prompt Category and Prompt selectors are shown side-by-side on desktop.
	- Output Types are displayed in a horizontal row with responsive wrapping when space is limited.
5. Click **Add Job To Queue**.

	- Correction behavior follows shared runtime configuration in `readme.md`; `AI Only Corrections: true` keeps output strictly model-provided.
	- Objective guardrails still remove invalid terminal punctuation appends such as `?.`, `!.`, and `:.`.
	- `Retry On Empty Corrections: true` retries non-trivial empty correction results once at temperature `0.0`.
Prompt notes:
- Prompt lists include versioned entries (baseline `1.0`).
- Prompt catalogs are loaded from `prompts/prod` and `prompts/staging`.
- Human-readable prompt editing uses `.prompt.md` files.
- Startup automatically regenerates matching JSON prompt files from markdown.
- A `Staging` prompt category is available for testing prompt variants before promoting to production by manual file copy.
- If multiple production versions exist for one prompt lineage, only the latest production version is shown for selection.
- Markdown files are the source of truth for prompt edits.
- Staging markdown filenames are normalized with version suffixes (example: `default_v1_1.prompt.md`) for easier editing.
- Prompt labels in dropdowns include version in the prompt name.

Provider/model/prompt/output-type selections are persisted server-side as shared defaults, so new browser sessions and other users see the same defaults.
Provider choices in the wizard are filtered to configured and reachable providers only. Local providers are checked with a short timeout so unavailable hosts do not appear.
Azure AI Foundry provider entries are also grouped by configured vendor category, and only vendor categories with at least one configured model are shown.

## Hidden Whitespace Handling

The tool automatically detects and normalizes invisible Unicode whitespace characters in source documents before analysis. This prevents false-positive corrections when spacing is visually correct but hidden characters are present. Normalized text is used during LLM analysis, and corrections caused purely by invisible whitespace are dropped automatically.
Correction sanitation also blocks duplicate terminal punctuation artifacts during list-item punctuation fixes so outputs do not gain trailing `..`.

For process jobs, each completed run also updates:
- `output/<folder>/summary_report_state.json` (historical execution stats)
- `output/<folder>/summary_report.docx` (auto-generated report from those stats)

### Queue

Monitors all running and historical jobs (last 20 shown):

- **Current Run** — shows active job and status message.
- **Logs** — live tail of execution, performance, or raw LLM logs (10 visible lines, scrollable).
  Raw LLM log entries are stored in `output/llm_raw_output.log` with explicit `--- INPUT ---` and `--- OUTPUT ---` blocks and a 10 MB maximum file size.
- **Queue** — compact list with Cancel (queued/running) and Retry (failed/canceled/completed) buttons.
	- Shows files/URLs plus total corrections and token usage per job: input, output, and combined tokens.

Queue state is saved to `output/web_job_history.json`. Queued jobs survive server restarts.

### Files

Browse input and output folders:

- Select scope (Input / Output) and a folder.
- After choosing or creating a folder in Wizard, the Files tab defaults to that folder under Output the next time Files is opened.
- Files are listed by name with size and modification time.
- Click **Download** to download a single file.
- Click **Generate ZIP** to generate a zip archive in the corresponding output folder.

## Remote debugging

The web server can also act as a diagnostics receiver for a separate remote host.

- Remote systems can `POST` captured bundles to `/api/debug/upload`.
- Received bundles are stored under `output/debug_bundles/`.
- You can inspect received bundles with `/api/debug/bundles` or analyze one immediately with `/api/debug/analyze`.
- Use `/api/debug/health-check` from the remote host first to confirm network reachability.

For the full workflow and integration examples, see [remote_debugging.md](remote_debugging.md).

## Uploading ZIP files

Drop or choose a `.zip` file in the Wizard upload area. The server will:

1. Save the `.zip` to the input folder (it will be visible in the Files tab).
2. Extract all contents into the same folder in the background.
3. Log extraction progress to `output/execution.log`.

All `output/...` examples above are relative to the output root configured in `paths.json`.

ZIP files are not processable by the correction engine — only `.docx`, `.mhtml`, and `.pdf` are picked up.

For Download + Process jobs, `.mhtml` sources are cleaned up after successful conversion so the input folder is left with `.docx` processing files.

## Configuration and environment setup

All provider variables, runtime keys, and environment setup are documented in [configuration.md](configuration.md).
Selected provider/model/prompt/output-type defaults are persisted and shared across sessions/users.

Recommended setup order:

1. Run `python setup_foundry_env.py` (or configure provider environment variables in [configuration.md](configuration.md)).
2. Restart the web server.
3. Open Wizard → Advanced Options and confirm model entries appear.
4. If using multiple Foundry profiles or vendors, select the desired vendor/provider category and profile-qualified model entry before queueing a job.

Notes:
- `python setup_foundry_env.py` writes both USER and MACHINE scope variables by default for multi-user consistency.
- Run setup from an elevated session, then restart the `DocumentCorrectionToolkitWeb` service.
- Use `python setup_foundry_env.py --scope user` only for local single-user runs.

## Web UI troubleshooting

- **Provider shows no models in wizard** — Ensure Ollama or LM Studio server is running, or Azure AI Foundry env vars are set. Re-run `python setup_foundry_env.py` from an elevated session to synchronize USER and MACHINE profiles, then restart the app/service.
- **Azure AI Foundry model calls fail for gpt-4o-mini** — Set `AZURE_AI_FOUNDRY_ENDPOINT` to `https://<resource>.cognitiveservices.azure.com/` and set `AZURE_AI_FOUNDRY_API_VERSION` to a compatible preview (for example `2025-01-01-preview`).
- **No files appear in file selection** — File selection is shown for **Process Existing Files** task type. Switch task type to process existing files, then choose the input folder.
- **MHTML conversion fails with CoInitialize error** — This was a background-thread COM issue. It is fixed in `convert.py` (v1.1+). Restart the server after pulling the latest code.
- **Job stuck as queued** — Worker thread may have crashed. Restart the server; queued jobs will be restored from history.
- **Generate ZIP returns 400** — No files in the selected folder. Switch scope/folder or upload first.
- **ZIP extraction not completing** — Check `output/execution.log` for `[zip-extract]` entries to see errors.
- **Remote host cannot upload a bundle** — Verify port `8000` is reachable from the remote machine and test `/api/debug/health-check` using the developer machine IP, not `127.0.0.1`.
- **Windows service starts then stops immediately** — Check `output/web_service.log` and `output/web_service_error.log`. The most common causes are missing Python dependencies or port `8000` already being in use.
- **Service is reachable only locally** — Reinstall or restart with `-Host 0.0.0.0`, then open the firewall with `-OpenFirewall` if remote clients need access.

## API contract

For programmatic access or building a separate frontend, see [api_contract.md](api_contract.md).
