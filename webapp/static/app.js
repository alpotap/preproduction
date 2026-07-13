const state = {
  capabilities: null,
  currentLogKind: 'execution',
  currentScope: 'input',
  promptMap: {},
  promptAbbrMap: {},
  selectableFiles: [],
  wizardFilesDefaultFolder: '',
  pendingWizardFilesDefault: false,
};

const elements = {
  heroStatus: document.getElementById('heroStatus'),
  tabline: document.getElementById('tabline'),
  tabButtons: document.querySelectorAll('.tab-button'),
  tabPanels: document.querySelectorAll('.tab-panel'),
  taskType: document.getElementById('taskType'),
  folderSelect: document.getElementById('folderSelect'),
  newFolderName: document.getElementById('newFolderName'),
  createFolderButton: document.getElementById('createFolderButton'),
  fileSelectBlock: document.getElementById('fileSelectBlock'),
  selectableFilesList: document.getElementById('selectableFilesList'),
  selectableFilesNote: document.getElementById('selectableFilesNote'),
  selectAllFilesButton: document.getElementById('selectAllFilesButton'),
  clearFilesButton: document.getElementById('clearFilesButton'),
  uploadUrlsStep: document.getElementById('uploadUrlsStep'),
  urlsInput: document.getElementById('urlsInput'),
  promptCategorySelect: document.getElementById('promptCategorySelect'),
  promptSelect: document.getElementById('promptSelect'),
  notifyTerminalPunctuationOn: document.getElementById('notifyTerminalPunctuationOn'),
  notifyTerminalPunctuationOff: document.getElementById('notifyTerminalPunctuationOff'),
  outputTypeList: document.getElementById('outputTypeList'),
  promptTooltipText: document.getElementById('promptTooltipText'),
  enqueueJobButton: document.getElementById('enqueueJobButton'),
  jobMessage: document.getElementById('jobMessage'),
  currentRunCard: document.getElementById('currentRunCard'),
  jobsList: document.getElementById('jobsList'),
  logKindSelect: document.getElementById('logKindSelect'),
  logViewer: document.getElementById('logViewer'),
  browserScopeSelect: document.getElementById('browserScopeSelect'),
  browserFolderSelect: document.getElementById('browserFolderSelect'),
  fileTable: document.getElementById('fileTable'),
  refreshStatusButton: document.getElementById('refreshStatusButton'),
  refreshJobsButton: document.getElementById('refreshJobsButton'),
  refreshLogsButton: document.getElementById('refreshLogsButton'),
  refreshFilesButton: document.getElementById('refreshFilesButton'),
  downloadAllButton: document.getElementById('downloadAllButton'),
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function humanSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatTimestamp(value) {
  if (!value) return '—';
  const date = new Date(value);
  return date.toLocaleString();
}

function formatDuration(startValue, endValue) {
  if (!startValue || !endValue) return '';
  const start = new Date(startValue);
  const end = new Date(endValue);
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  if (minutes > 0) return `${minutes}m ${remaining}s`;
  return `${remaining}s`;
}

function formatCount(value) {
  const parsed = Number(value || 0);
  if (!Number.isFinite(parsed)) return '0';
  return parsed.toLocaleString();
}

function fileIconClass(extension) {
  const ext = (extension || '').replace('.', '').toLowerCase();
  if (['docx'].includes(ext)) return 'docx';
  if (['pdf'].includes(ext)) return 'pdf';
  if (['mhtml', 'html'].includes(ext)) return 'mhtml';
  if (['txt', 'csv', 'log', 'md'].includes(ext)) return ext;
  if (ext === 'zip') return 'other';
  return 'default';
}

function getOutputTagInfo(fileName) {
  const normalized = (fileName || '').toLowerCase();
  if (normalized.includes('corrected_inline')) return { code: 'INL', tip: 'Inline output with comments and deletion markers.' };
  if (normalized.includes('corrected_uncommented')) return { code: 'UNC', tip: 'Inline output without comments and without deletion markers.' };
  if (normalized.includes('corrected_track_changes')) return { code: 'TRK', tip: 'Microsoft Word Track Changes output with reviewable revisions.' };
  if (normalized.includes('corrected_hybrid')) return { code: 'HYB', tip: 'Hybrid output: inline corrections with Word comments.' };
  if (normalized.includes('consistency_analysis')) return { code: 'CNS', tip: 'Consistency analysis report output.' };
  return null;
}

function getPromptTagInfo(fileName) {
  const match = /_([A-Za-z]{2,8})_corrected_/i.exec(fileName || '');
  if (!match) return null;
  const code = (match[1] || '').toUpperCase();
  if (!code) return null;
  const prompt = state.promptAbbrMap[code];
  if (!prompt) return null;
  return {
    code: prompt.abbr || code,
    tip: `${prompt.name}: ${prompt.summary}`,
  };
}

function escapeHtmlAttribute(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function setMessage(target, message, isError = false) {
  target.textContent = message || '';
  target.style.color = isError ? '#b52121' : '';
}

function notifyTerminalPunctuationEnabled() {
  return Boolean(elements.notifyTerminalPunctuationOn?.checked);
}

function setNotifyTerminalPunctuation(enabled) {
  const isEnabled = enabled !== false;
  if (elements.notifyTerminalPunctuationOn) {
    elements.notifyTerminalPunctuationOn.checked = isEnabled;
  }
  if (elements.notifyTerminalPunctuationOff) {
    elements.notifyTerminalPunctuationOff.checked = !isEnabled;
  }
}

function updateWindowLayoutClass() {
  const threshold = (window.screen?.availWidth || window.innerWidth) * 0.5;
  document.body.classList.toggle('wide-window', window.innerWidth >= threshold);
}

async function loadCapabilities() {
  state.capabilities = await fetchJson('/api/capabilities');
  renderCapabilities();
}

function renderCapabilities() {
  const {
    prompts = [],
    promptCategories = [],
    outputTypes = [],
    config = {},
  } = state.capabilities || {};
  state.promptMap = Object.fromEntries(prompts.map(prompt => [prompt.key, prompt]));
  state.promptAbbrMap = Object.fromEntries(
    prompts
      .filter(prompt => prompt.abbr)
      .map(prompt => [String(prompt.abbr).toUpperCase(), prompt]),
  );

  // Populate category dropdown
  const categories = promptCategories || [];
  elements.promptCategorySelect.innerHTML = categories
    .map(cat => `<option value="${cat.key}">${cat.label}</option>`)
    .join('');

  // Load prompt from sessionStorage or default to "Full Copy Edit"
  let sessionPromptKey = null;
  try {
    sessionPromptKey = JSON.parse(sessionStorage.getItem('sessionPromptKey'));
  } catch {
    // Ignore parse errors
  }
  
  // Try to find "Full Copy Edit" prompt as default
  const fullCopyEditPrompt = prompts.find(p => p.name === 'Full Copy Edit');
  const defaultPromptKey = sessionPromptKey || fullCopyEditPrompt?.key || config.activePrompt;
  const activePrompt = state.promptMap[defaultPromptKey];
  const initialCategory = activePrompt?.category || (categories[0]?.key ?? '');
  elements.promptCategorySelect.value = initialCategory;

  // Populate prompt dropdown filtered to selected category
  filterPromptsByCategory(initialCategory, defaultPromptKey);

  setNotifyTerminalPunctuation(config.notifyTerminalPunctuation !== false);

  // Load output types from sessionStorage or default to ["Hybrid"]
  let sessionOutputTypes = null;
  try {
    sessionOutputTypes = JSON.parse(sessionStorage.getItem('sessionOutputTypes'));
  } catch {
    // Ignore parse errors
  }
  
  const defaultOutputTypes = sessionOutputTypes || ['Hybrid'];

  elements.outputTypeList.innerHTML = outputTypes
    .map(outputType => {
      const checked = defaultOutputTypes.includes(outputType.key) ? 'checked' : '';
      return `
        <label class="checkbox-item">
          <input type="checkbox" value="${outputType.key}" ${checked}>
          <span>${outputType.label}</span>
        </label>
      `;
    })
    .join('');
}

function updatePromptTooltip() {
  const prompt = state.promptMap[elements.promptSelect.value];
  elements.promptTooltipText.textContent = prompt?.details || prompt?.summary || 'Prompt details unavailable.';
}

function filterPromptsByCategory(categoryKey, preferredPromptKey = null) {
  const prompts = state.capabilities?.prompts || [];
  const filtered = prompts.filter(p => p.category === categoryKey);
  elements.promptSelect.innerHTML = filtered
    .map(p => `<option value="${p.key}">${p.name}</option>`)
    .join('');
  // Prefer the currently active prompt if it belongs to this category, otherwise pick first
  if (preferredPromptKey && filtered.some(p => p.key === preferredPromptKey)) {
    elements.promptSelect.value = preferredPromptKey;
  } else if (filtered.length > 0) {
    elements.promptSelect.value = filtered[0].key;
  }
  updatePromptTooltip();
}

async function persistPreferences(overrides = {}) {
  // Save prompt and output types to sessionStorage (session-only)
  const promptKey = elements.promptSelect.value || null;
  const outputTypes = selectedOutputTypes();
  sessionStorage.setItem('sessionPromptKey', JSON.stringify(promptKey));
  sessionStorage.setItem('sessionOutputTypes', JSON.stringify(outputTypes));

  const payload = {
    promptKey,
    outputTypes,
    notifyTerminalPunctuation: notifyTerminalPunctuationEnabled(),
    ...overrides,
  };

  await fetchJson('/api/preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (state.capabilities?.config) {
    if (payload.notifyTerminalPunctuation !== null && payload.notifyTerminalPunctuation !== undefined) {
      state.capabilities.config.notifyTerminalPunctuation = payload.notifyTerminalPunctuation;
      setNotifyTerminalPunctuation(payload.notifyTerminalPunctuation);
    }
  }
}

async function loadFolders(scope = 'input', selectEl = elements.folderSelect) {
  const data = await fetchJson(`/api/folders?scope=${encodeURIComponent(scope)}`);
  const folders = data.folders || [];
  selectEl.innerHTML = folders.length
    ? folders.map(folder => `<option value="${folder}">${folder}</option>`).join('')
    : '<option value="">No folders yet</option>';
}

async function createFolder() {
  const name = elements.newFolderName.value.trim();
  if (!name) {
    setMessage(elements.jobMessage, 'Folder name is required.', true);
    return;
  }
  try {
    await fetchJson('/api/folders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    elements.newFolderName.value = '';
    await loadFolders('input', elements.folderSelect);
    elements.folderSelect.value = name;
    queueFilesTabDefaultFromWizardFolder();
    await refreshSelectableFiles();
    if (document.getElementById('filesTab')?.classList.contains('active')) {
      await applyFilesTabDefaultFromWizardFolder();
    }
    setMessage(elements.jobMessage, `Created folder ${name}.`);
  } catch (error) {
    setMessage(elements.jobMessage, error.message, true);
  }
}

async function uploadFiles(fileList) {
  const uploadMessageTarget = elements.selectableFilesNote || elements.jobMessage;
  const folder = elements.folderSelect.value;
  if (!folder) {
    setMessage(uploadMessageTarget, 'Choose or create an input folder first.', true);
    return;
  }
  if (!fileList.length) {
    return;
  }

  const formData = new FormData();
  for (const file of fileList) {
    formData.append('files', file);
  }

  try {
    const result = await fetchJson(`/api/uploads?folder=${encodeURIComponent(folder)}`, {
      method: 'POST',
      body: formData,
    });
    const saved = result.saved?.length || 0;
    const rejected = result.rejected?.length || 0;
    const extracted = result.extractionStarted?.length || 0;
    const extractionNote = extracted ? ` ZIP extraction started for ${extracted} file(s).` : '';
    setMessage(uploadMessageTarget, `Uploaded ${saved} file(s). Rejected ${rejected}.${extractionNote}`);
    await refreshSelectableFiles();
    await refreshFileBrowser();
  } catch (error) {
    setMessage(uploadMessageTarget, error.message, true);
  }
}

function selectedOutputTypes() {
  if (!elements.outputTypeList) {
    return [];
  }
  return Array.from(elements.outputTypeList.querySelectorAll('input:checked')).map(input => input.value);
}

function selectedInputFiles() {
  return Array.from(elements.selectableFilesList.querySelectorAll('input[type="checkbox"]:checked')).map(input => input.value);
}

function updateSelectableFilesVisibility() {
  const usesFileSelection = ['process', 'render_cached'].includes(elements.taskType.value);
  elements.fileSelectBlock.hidden = !usesFileSelection;
  if (!usesFileSelection) {
    setMessage(elements.selectableFilesNote, 'File selection is available for Process existing files and Generate outputs from saved AI run.');
  }
}

function updateUploadUrlsVisibility() {
  const isDownloadTask = elements.taskType.value === 'download_process';
  if (elements.uploadUrlsStep) {
    elements.uploadUrlsStep.hidden = !isDownloadTask;
  }
}

function queueFilesTabDefaultFromWizardFolder() {
  state.wizardFilesDefaultFolder = elements.folderSelect.value || '';
  state.pendingWizardFilesDefault = Boolean(state.wizardFilesDefaultFolder);
}

async function applyFilesTabDefaultFromWizardFolder() {
  if (!state.pendingWizardFilesDefault) {
    return;
  }
  const preferredFolder = state.wizardFilesDefaultFolder || elements.folderSelect.value || '';
  await refreshFileBrowser(preferredFolder, 'output');
  state.pendingWizardFilesDefault = false;
}

async function refreshSelectableFiles() {
  const folder = elements.folderSelect.value;
  const taskType = elements.taskType.value;
  if (!folder) {
    state.selectableFiles = [];
    elements.selectableFilesList.innerHTML = '';
    setMessage(elements.selectableFilesNote, 'Select an input folder to choose files.');
    return;
  }

  try {
    const data = await fetchJson(
      `/api/processable-files?folder=${encodeURIComponent(folder)}&taskType=${encodeURIComponent(taskType)}`,
    );
    const rawFiles = Array.isArray(data.files) ? data.files : [];
    state.selectableFiles = rawFiles
      .map(item => {
        if (typeof item === 'string') {
          return {
            name: item,
            sizeBytes: 0,
            modifiedAt: null,
            lastProcessedAt: null,
          };
        }
        if (item && typeof item === 'object') {
          return {
            name: String(item.name || '').trim(),
            sourceName: String(item.sourceName || item.name || '').trim(),
            promptKey: String(item.promptKey || '').trim(),
            promptName: String(item.promptName || '').trim(),
            selectionValue: String(item.selectionValue || item.name || '').trim(),
            cacheReady: Boolean(item.cacheReady),
            cacheStatus: String(item.cacheStatus || ''),
            cacheSavedAt: item.cacheSavedAt || null,
            correctionCount: Number(item.correctionCount || 0),
            sizeBytes: Number(item.sizeBytes || 0),
            modifiedAt: item.modifiedAt || null,
            lastProcessedAt: item.lastProcessedAt || null,
          };
        }
        return null;
      })
      .filter(item => item && item.name);

    if (!state.selectableFiles.length) {
      elements.selectableFilesList.innerHTML = '';
      const emptyMessage = taskType === 'render_cached'
        ? 'No cached runs found for this folder yet. Run Process existing files first.'
        : 'No processable files (.docx, .mhtml, .pdf) found in this folder.';
      setMessage(elements.selectableFilesNote, emptyMessage);
      return;
    }

    if (taskType === 'render_cached') {
      const renderEntries = state.selectableFiles.filter(entry => entry.cacheReady);
      if (!renderEntries.length) {
        elements.selectableFilesList.innerHTML = '';
        setMessage(elements.selectableFilesNote, 'No cache-ready runs found in this folder for current source files.');
        return;
      }

      const grouped = renderEntries.reduce((acc, entry) => {
        const key = entry.sourceName || entry.name;
        if (!acc[key]) {
          acc[key] = [];
        }
        acc[key].push(entry);
        return acc;
      }, {});

      const sourceNames = Object.keys(grouped).sort((a, b) => a.localeCompare(b));
      elements.selectableFilesList.innerHTML = sourceNames
        .map(sourceName => {
          const groupEntries = grouped[sourceName];
          const groupRows = groupEntries
            .map(entry => {
              const runLabel = entry.promptName || entry.promptKey || 'Unknown prompt';
              const lastProcessed = entry.lastProcessedAt ? formatTimestamp(entry.lastProcessedAt) : 'Not processed yet';
              const correctionCount = Number.isFinite(entry.correctionCount) ? entry.correctionCount : 0;
              return `
                <label class="checkbox-item selectable-file-item" title="${escapeHtmlAttribute(sourceName)} — ${escapeHtmlAttribute(runLabel)}">
                  <input type="checkbox" value="${escapeHtmlAttribute(entry.selectionValue)}" data-source-name="${escapeHtmlAttribute(sourceName)}" checked>
                  <span class="selectable-file-name">${sourceName} · ${runLabel}</span>
                  <span class="selectable-file-meta">Last processed: ${lastProcessed} · Corrections: ${formatCount(correctionCount)}</span>
                </label>
              `;
            })
            .join('');

          return `
            <div class="selectable-file-group">
              <div class="selectable-file-group-header">
                <span class="selectable-file-group-title">${sourceName}</span>
                <button class="button ghost selectable-file-group-action" type="button" data-action="select-source-runs" data-source-name="${escapeHtmlAttribute(sourceName)}">All runs</button>
              </div>
              ${groupRows}
            </div>
          `;
        })
        .join('');

      elements.selectableFilesList
        .querySelectorAll('button[data-action="select-source-runs"]')
        .forEach(button => {
          button.addEventListener('click', () => {
            const sourceName = button.dataset.sourceName || '';
            elements.selectableFilesList
              .querySelectorAll('input[type="checkbox"][data-source-name]')
              .forEach(input => {
                if (input.dataset.sourceName === sourceName && !input.disabled) {
                  input.checked = true;
                }
              });
          });
        });

      setMessage(elements.selectableFilesNote, `${renderEntries.length} cached run entries available.`);
      return;
    }

    elements.selectableFilesList.innerHTML = state.selectableFiles
      .map(file => {
        const name = file.name || '';
        const size = file.sizeBytes > 0 ? humanSize(file.sizeBytes) : 'Unknown size';
        const lastProcessed = file.lastProcessedAt ? formatTimestamp(file.lastProcessedAt) : 'Not processed yet';
        return `
        <label class="checkbox-item selectable-file-item" title="${escapeHtmlAttribute(name)}">
          <input type="checkbox" value="${escapeHtmlAttribute(file.selectionValue || name)}" checked>
          <span class="selectable-file-name">${name}</span>
          <span class="selectable-file-meta">Last processed: ${lastProcessed} · ${size}</span>
        </label>
      `;
      })
      .join('');
    setMessage(elements.selectableFilesNote, `${state.selectableFiles.length} file(s) available.`);
  } catch (error) {
    state.selectableFiles = [];
    elements.selectableFilesList.innerHTML = '';
    setMessage(elements.selectableFilesNote, error.message, true);
  }
}

function selectAllInputFiles(checked) {
  elements.selectableFilesList.querySelectorAll('input[type="checkbox"]').forEach(input => {
    input.checked = checked;
  });
}

async function enqueueJob() {
  const payload = {
    taskType: elements.taskType.value,
    folder: elements.folderSelect.value,
    promptKey: elements.promptSelect.value,
    outputTypes: selectedOutputTypes(),
    notifyTerminalPunctuation: notifyTerminalPunctuationEnabled(),
    urls: elements.urlsInput.value,
    selectedFiles: selectedInputFiles(),
  };

  if (!payload.folder) {
    setMessage(elements.jobMessage, 'Select an input folder.', true);
    return;
  }
  if (payload.taskType === 'download_process' && !payload.urls.trim()) {
    setMessage(elements.jobMessage, 'Add at least one URL for Download and process jobs.', true);
    return;
  }
  if (['process', 'render_cached'].includes(payload.taskType) && !payload.selectedFiles.length) {
    const taskHint = payload.taskType === 'render_cached'
      ? 'Select at least one source file. If the list is missing after restart, refresh the page once.'
      : 'Select at least one file.';
    setMessage(elements.jobMessage, taskHint, true);
    return;
  }
  if (!['process', 'render_cached'].includes(payload.taskType)) {
    payload.selectedFiles = [];
  }

  try {
    await fetchJson('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    setMessage(elements.jobMessage, 'Job added to queue.');
    elements.urlsInput.value = '';
    await Promise.all([refreshStatus(), refreshJobs()]);
  } catch (error) {
    setMessage(elements.jobMessage, error.message, true);
  }
}

async function refreshStatus() {
  const status = await fetchJson('/api/status');
  const currentRun = status.currentRun;
  const telemetry = status.telemetry || {};
  const telemetryLine = `Workers active: ${Number(telemetry.activeParallelFileWorkers || 0)} (peak ${Number(telemetry.peakParallelFileWorkers || 0)}) · LLM inflight: ${Number(telemetry.llmInflightRequests || 0)} · LLM waiters: ${Number(telemetry.llmQueueWaiters || 0)} · Avg queue wait: ${Number(telemetry.averageQueueWaitMs || 0).toFixed(2)} ms`;
  elements.heroStatus.textContent = currentRun ? currentRun.status.toUpperCase() : 'IDLE';
  elements.currentRunCard.classList.toggle('empty', !currentRun);
  if (!currentRun) {
    elements.currentRunCard.innerHTML = `
      <div class="run-meta">No active job.</div>
      <div class="run-meta">${telemetryLine}</div>
    `;
    return;
  }
  elements.currentRunCard.innerHTML = `
    <div class="job-top">
      <strong>${currentRun.taskType}</strong>
      <span class="badge ${currentRun.status}">${currentRun.status}</span>
    </div>
    <div class="run-meta">Folder: ${currentRun.folder}</div>
    <div class="run-meta">Started: ${formatTimestamp(currentRun.startedAt)}</div>
    <div class="run-meta">${currentRun.currentMessage || 'Running'}</div>
    <div class="run-meta">${telemetryLine}</div>
  `;
}

async function refreshJobs() {
  const data = await fetchJson('/api/jobs');
  const jobs = (data.jobs || []).slice(0, 20);
  if (!jobs.length) {
    elements.jobsList.className = 'jobs-list empty';
    elements.jobsList.textContent = 'No jobs queued yet.';
    return;
  }
  elements.jobsList.className = 'jobs-list';
  elements.jobsList.innerHTML = jobs.map(job => {
    const cancelBtn = (job.status === 'queued' || job.status === 'running')
      ? `<button class="button ghost" data-action="cancel" data-id="${job.id}">Cancel</button>` : '';
    const retryBtn = (job.status === 'failed' || job.status === 'canceled' || job.status === 'completed')
      ? `<button class="button ghost" data-action="retry" data-id="${job.id}">Retry</button>` : '';

    const detailTokens = [];
    if (job.processedFiles) detailTokens.push(`${job.processedFiles} files`);
    if (job.downloadedUrls) detailTokens.push(`${job.downloadedUrls} urls`);
    if (job.correctionCount) detailTokens.push(`${formatCount(job.correctionCount)} corrections`);
    if (job.totalInputTokens) detailTokens.push(`in ${formatCount(job.totalInputTokens)} tok`);
    if (job.totalTokensGenerated) detailTokens.push(`out ${formatCount(job.totalTokensGenerated)} tok`);
    if (job.totalTokens) detailTokens.push(`total ${formatCount(job.totalTokens)} tok`);
    const duration = formatDuration(job.startedAt, job.finishedAt);
    if (duration) detailTokens.push(`time ${duration}`);

    return `
      <div class="job-row">
        <span class="badge ${job.status}">${job.status}</span>
        <div class="job-row-info">
          <span class="job-row-name">${job.taskType} — ${job.folder}</span>
          <span class="job-row-msg">${job.currentMessage || ''}</span>
          ${detailTokens.length ? `<span class="job-row-stats">${detailTokens.join(' · ')}</span>` : ''}
        </div>
        <span class="job-row-time">${formatTimestamp(job.createdAt)}</span>
        <div class="job-actions">${cancelBtn}${retryBtn}</div>
      </div>
    `;
  }).join('');

  elements.jobsList.querySelectorAll('button[data-action="cancel"]').forEach(button => {
    button.addEventListener('click', () => cancelJob(button.dataset.id));
  });
  elements.jobsList.querySelectorAll('button[data-action="retry"]').forEach(button => {
    button.addEventListener('click', () => retryJob(button.dataset.id));
  });
}

async function cancelJob(jobId) {
  try {
    await fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
    setMessage(elements.jobMessage, 'Cancellation submitted.');
    await Promise.all([refreshStatus(), refreshJobs()]);
  } catch (error) {
    setMessage(elements.jobMessage, error.message, true);
  }
}

async function retryJob(jobId) {
  try {
    await fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/retry`, { method: 'POST' });
    setMessage(elements.jobMessage, 'Retry job queued.');
    await Promise.all([refreshStatus(), refreshJobs()]);
  } catch (error) {
    setMessage(elements.jobMessage, error.message, true);
  }
}

async function refreshLogs() {
  const kind = elements.logKindSelect.value;
  state.currentLogKind = kind;
  const data = await fetchJson(`/api/logs/${encodeURIComponent(kind)}?lines=300`);
  elements.logViewer.textContent = data.content || 'No log content yet.';
  elements.logViewer.scrollTop = elements.logViewer.scrollHeight;
}

async function refreshFileBrowser(preferredFolder = null, preferredScope = null) {
  // Guard against DOM change event objects being passed by listeners.
  if (preferredFolder && typeof preferredFolder === 'object' && 'target' in preferredFolder) {
    preferredFolder = null;
  }
  if (preferredScope && typeof preferredScope === 'object' && 'target' in preferredScope) {
    preferredScope = null;
  }

  if (preferredScope) {
    elements.browserScopeSelect.value = preferredScope;
  }

  const scope = elements.browserScopeSelect.value;
  const previousFolder = preferredFolder || elements.browserFolderSelect.value;
  await loadFolders(scope, elements.browserFolderSelect);

  const folderOptions = Array.from(elements.browserFolderSelect.options).map(option => option.value).filter(Boolean);
  if (previousFolder && folderOptions.includes(previousFolder)) {
    elements.browserFolderSelect.value = previousFolder;
  } else if (preferredFolder) {
    elements.browserFolderSelect.innerHTML = `<option value="${preferredFolder}">${preferredFolder}</option>${elements.browserFolderSelect.innerHTML}`;
    elements.browserFolderSelect.value = preferredFolder;
  } else if (folderOptions.length) {
    elements.browserFolderSelect.value = folderOptions[0];
  }

  const selectedFolder = elements.browserFolderSelect.value;
  if (!selectedFolder) {
    elements.fileTable.className = 'file-table empty';
    elements.fileTable.textContent = 'Select a folder to view files.';
    return;
  }

  const url = `/api/files?scope=${encodeURIComponent(scope)}&folder=${encodeURIComponent(selectedFolder)}&limit=50&skip=0`;
  const data = await fetchJson(url);
  const files = data.files || [];
  if (!files.length) {
    elements.fileTable.className = 'file-table empty';
    elements.fileTable.textContent = 'No files in this folder.';
    return;
  }
  elements.fileTable.className = 'file-table';
  elements.fileTable.innerHTML = `
    <div class="file-header">
      <span>Name</span>
      <span>Size</span>
      <span>Modified</span>
      <span>Download</span>
    </div>
    ${files.map(file => `
      ${(() => {
        const outputInfo = getOutputTagInfo(file.name);
        const promptInfo = getPromptTagInfo(file.name);
        const outputTag = outputInfo
          ? `<span class="output-pill" title="${escapeHtmlAttribute(outputInfo.tip)}">${outputInfo.code}</span>`
          : '';
        const promptTag = promptInfo
          ? `<span class="output-pill prompt-pill" title="${escapeHtmlAttribute(promptInfo.tip)}">${promptInfo.code}</span>`
          : '';
        return `
      <div class="file-row">
        <div class="file-name">
          <span class="file-icon ${fileIconClass(file.extension)}"></span>
          <a href="${file.downloadUrl}" target="_blank" rel="noopener">${file.name}</a>
          ${outputTag}
          ${promptTag}
        </div>
        <div class="file-meta">${humanSize(file.sizeBytes)}</div>
        <div class="file-meta">${formatTimestamp(file.modifiedAt)}</div>
        <div><a class="button ghost" href="${file.downloadUrl}">Download</a></div>
      </div>
    `;
      })()}
    `).join('')}
  `;
}

async function switchTab(tabId) {
  elements.tabButtons.forEach(button => {
    button.classList.toggle('active', button.dataset.tab === tabId);
  });
  elements.tabPanels.forEach(panel => {
    panel.classList.toggle('active', panel.id === tabId);
  });

  if (tabId === 'filesTab') {
    await applyFilesTabDefaultFromWizardFolder();
  }
}

async function generateCurrentFolderZip(event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }

  const scope = elements.browserScopeSelect.value;
  const folder = elements.browserFolderSelect.value;
  if (!folder) {
    setMessage(elements.jobMessage, 'Select a folder in Files tab first.', true);
    return;
  }
  try {
    const payload = await fetchJson(`/api/download-zip?scope=${encodeURIComponent(scope)}&folder=${encodeURIComponent(folder)}`);

    // Keep the user anchored in Files and switch to the generated output location.
    await switchTab('filesTab');
    elements.browserScopeSelect.value = 'output';
    await loadFolders('output', elements.browserFolderSelect);
    if (payload.outputFolder && Array.from(elements.browserFolderSelect.options).some(option => option.value === payload.outputFolder)) {
      elements.browserFolderSelect.value = payload.outputFolder;
    }
    await refreshFileBrowser();
    setMessage(elements.jobMessage, `ZIP generated: ${payload.outputRelativePath}`);
  } catch (error) {
    setMessage(elements.jobMessage, error.message, true);
  }
}

function bindEvents() {
  window.addEventListener('resize', updateWindowLayoutClass);
  elements.tabButtons.forEach(button => {
    button.addEventListener('click', () => {
      switchTab(button.dataset.tab).catch(error => setMessage(elements.jobMessage, error.message, true));
    });
  });

  elements.createFolderButton.addEventListener('click', createFolder);
  elements.folderSelect.addEventListener('change', refreshSelectableFiles);
  elements.folderSelect.addEventListener('change', () => {
    queueFilesTabDefaultFromWizardFolder();
    if (document.getElementById('filesTab')?.classList.contains('active')) {
      applyFilesTabDefaultFromWizardFolder().catch(error => setMessage(elements.jobMessage, error.message, true));
    }
  });
  elements.taskType.addEventListener('change', () => {
    updateSelectableFilesVisibility();
    updateUploadUrlsVisibility();
    if (['process', 'render_cached'].includes(elements.taskType.value)) {
      refreshSelectableFiles().catch(error => setMessage(elements.jobMessage, error.message, true));
    }
  });
  elements.selectAllFilesButton.addEventListener('click', () => selectAllInputFiles(true));
  elements.clearFilesButton.addEventListener('click', () => selectAllInputFiles(false));
  elements.enqueueJobButton.addEventListener('click', enqueueJob);
  [elements.notifyTerminalPunctuationOn, elements.notifyTerminalPunctuationOff]
    .filter(Boolean)
    .forEach(input => {
      input.addEventListener('change', async () => {
        try {
          await persistPreferences();
        } catch (error) {
          setMessage(elements.jobMessage, `Could not save punctuation notification setting: ${error.message}`, true);
        }
      });
    });
  elements.promptSelect.addEventListener('change', async () => {
    updatePromptTooltip();
    try {
      await persistPreferences();
    } catch (error) {
      setMessage(elements.jobMessage, `Could not save prompt preference: ${error.message}`, true);
    }
  });
  elements.promptCategorySelect.addEventListener('change', () =>
    filterPromptsByCategory(elements.promptCategorySelect.value),
  );
  elements.outputTypeList.addEventListener('change', async event => {
    if (event.target && event.target.matches('input[type="checkbox"]')) {
      try {
        await persistPreferences();
      } catch (error) {
        setMessage(elements.jobMessage, `Could not save output type selection: ${error.message}`, true);
      }
    }
  });
  elements.logKindSelect.addEventListener('change', refreshLogs);
  elements.browserScopeSelect.addEventListener('change', () => refreshFileBrowser());
  elements.browserFolderSelect.addEventListener('change', () => refreshFileBrowser());
  elements.refreshStatusButton.addEventListener('click', refreshStatus);
  elements.refreshJobsButton.addEventListener('click', refreshJobs);
  elements.refreshLogsButton.addEventListener('click', refreshLogs);
  elements.refreshFilesButton.addEventListener('click', refreshFileBrowser);
  elements.downloadAllButton.addEventListener('click', generateCurrentFolderZip);

  ['dragenter', 'dragover'].forEach(eventName => {
    elements.fileSelectBlock.addEventListener(eventName, event => {
      if (!['process', 'render_cached'].includes(elements.taskType.value)) {
        return;
      }
      event.preventDefault();
      elements.fileSelectBlock.classList.add('dragover');
    });
  });
  ['dragleave', 'drop'].forEach(eventName => {
    elements.fileSelectBlock.addEventListener(eventName, event => {
      if (!['process', 'render_cached'].includes(elements.taskType.value)) {
        return;
      }
      event.preventDefault();
      elements.fileSelectBlock.classList.remove('dragover');
    });
  });
  elements.fileSelectBlock.addEventListener('drop', event => {
    if (!['process', 'render_cached'].includes(elements.taskType.value)) {
      return;
    }
    uploadFiles(event.dataTransfer.files);
  });
}

async function bootstrap() {
  updateWindowLayoutClass();
  bindEvents();

  const capabilitiesTask = (async () => {
    try {
      await loadCapabilities();
    } catch (error) {
      setMessage(elements.jobMessage, `Capability load failed: ${error.message}`, true);
    }
  })();

  await loadFolders('input', elements.folderSelect);
  queueFilesTabDefaultFromWizardFolder();
  updateSelectableFilesVisibility();
  updateUploadUrlsVisibility();
  await refreshSelectableFiles();
  await refreshFileBrowser();
  await Promise.all([refreshStatus(), refreshJobs(), refreshLogs()]);
  await capabilitiesTask;
  window.setInterval(() => {
    refreshStatus();
    refreshJobs();
    refreshLogs();
  }, 3000);
}

bootstrap().catch(error => {
  setMessage(elements.jobMessage, error.message, true);
});
