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

1. Select task type (process, download+process, consistency).
2. Choose or create an input folder.
	- The Files To Process list shows each eligible file in a single full-width row with file size and last processed timestamp.
3. Upload files (drag-and-drop or file picker). ZIP files are extracted automatically in the background.
4. Paste URLs to download (for download tasks).
5. Choose prompt, provider, model, and output types.
6. Click **Add Job To Queue**.

For process jobs, each completed run also updates:
- `output/<folder>/summary_report_state.json` (historical execution stats)
- `output/<folder>/summary_report.docx` (auto-generated report from those stats)

### Queue

Monitors all running and historical jobs (last 20 shown):

- **Current Run** — shows active job and status message.
- **Logs** — live tail of execution, performance, or raw LLM logs (10 visible lines, scrollable).
- **Queue** — compact list with Cancel (queued/running) and Retry (failed/canceled/completed) buttons.

Queue state is saved to `output/web_job_history.json`. Queued jobs survive server restarts.

### Files

Browse input and output folders:

- Select scope (Input / Output) and a folder.
- Files are listed by name with size and modification time.
- Click **Download** to download a single file.
- Click **Download Folder ZIP** to download all files in the selected folder as a zip archive.

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

ZIP files are not processable by the correction engine — only `.docx`, `.mhtml`, and `.pdf` are picked up.

For Download + Process jobs, `.mhtml` sources are cleaned up after successful conversion so the input folder is left with `.docx` processing files.

## Configuration and environment setup

All provider variables, runtime keys, and environment setup are documented in [configuration.md](configuration.md).
For Azure AI Foundry, profile/model settings are environment-only and are not persisted in `readme.md`.

Recommended setup order:

1. Run `python setup_foundry_env.py` (or configure provider environment variables in [configuration.md](configuration.md)).
2. Restart the web server.
3. Open Wizard → Advanced Options and confirm model entries appear.
4. If using multiple Foundry profiles, select the profile-qualified model entry before queueing a job.

## Web UI troubleshooting

- **Provider shows no models in wizard** — Ensure Ollama or LM Studio server is running, or Azure AI Foundry env vars are set. Re-run `python setup_foundry_env.py` to regenerate profile variables quickly.
- **Azure AI Foundry model calls fail for gpt-4o-mini** — Set `AZURE_AI_FOUNDRY_ENDPOINT` to `https://<resource>.cognitiveservices.azure.com/` and set `AZURE_AI_FOUNDRY_API_VERSION` to a compatible preview (for example `2025-01-01-preview`).
- **No files appear in file selection** — File selection is shown for **Process Existing Files** task type. Switch task type to process existing files, then choose the input folder.
- **MHTML conversion fails with CoInitialize error** — This was a background-thread COM issue. It is fixed in `convert.py` (v1.1+). Restart the server after pulling the latest code.
- **Job stuck as queued** — Worker thread may have crashed. Restart the server; queued jobs will be restored from history.
- **Download Folder ZIP returns 400** — No files in the selected folder. Switch scope/folder or upload first.
- **ZIP extraction not completing** — Check `output/execution.log` for `[zip-extract]` entries to see errors.
- **Remote host cannot upload a bundle** — Verify port `8000` is reachable from the remote machine and test `/api/debug/health-check` using the developer machine IP, not `127.0.0.1`.
- **Windows service starts then stops immediately** — Check `output/web_service.log` and `output/web_service_error.log`. The most common causes are missing Python dependencies or port `8000` already being in use.
- **Service is reachable only locally** — Reinstall or restart with `-Host 0.0.0.0`, then open the firewall with `-OpenFirewall` if remote clients need access.

## API contract

For programmatic access or building a separate frontend, see [api_contract.md](api_contract.md).
