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

## Restarting the web server

The server has no live-reload. To restart after code or config changes:

1. Find the terminal or process running `local_web.py`.
2. Press `Ctrl+C` to stop it.
3. Run `py .\local_web.py` again (or `.\run_web.bat`).

If you started it with `run_web.bat` and the window is closed, just run it again — the job history file (`output/web_job_history.json`) will restore previously queued jobs automatically.

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
3. Upload files (drag-and-drop or file picker). ZIP files are extracted automatically in the background.
4. Paste URLs to download (for download tasks).
5. Choose prompt, provider, model, and output types.
6. Click **Add Job To Queue**.

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

## Uploading ZIP files

Drop or choose a `.zip` file in the Wizard upload area. The server will:

1. Save the `.zip` to the input folder (it will be visible in the Files tab).
2. Extract all contents into the same folder in the background.
3. Log extraction progress to `output/execution.log`.

ZIP files are not processable by the correction engine — only `.docx`, `.mhtml`, and `.pdf` are picked up.

## Configuration and environment setup

All provider variables, runtime keys, and environment setup are documented in [configuration.md](configuration.md).

## Web UI troubleshooting

- **Provider shows no models in wizard** — Ensure Ollama or LM Studio server is running, or Azure env vars are set.
- **MHTML conversion fails with CoInitialize error** — This was a background-thread COM issue. It is fixed in `convert.py` (v1.1+). Restart the server after pulling the latest code.
- **Job stuck as queued** — Worker thread may have crashed. Restart the server; queued jobs will be restored from history.
- **Download Folder ZIP returns 400** — No files in the selected folder. Switch scope/folder or upload first.
- **ZIP extraction not completing** — Check `output/execution.log` for `[zip-extract]` entries to see errors.

## API contract

For programmatic access or building a separate frontend, see [api_contract.md](api_contract.md).
