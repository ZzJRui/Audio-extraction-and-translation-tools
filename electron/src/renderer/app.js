(function initApp() {
  const MODE_LABELS = {
    original: "原文",
    translation: "译文",
    bilingual: "双语",
  };

  const STATUS_CAPTIONS = {
    idle: "选择音频和字幕模式后即可开始任务。",
    validating: "正在检查运行环境与任务参数。",
    running_transcribe: "正在执行语音识别，请稍候。",
    running_translate: "正在进行翻译，请留意日志输出。",
    running_export: "正在导出字幕文件，即将完成。",
    success: "任务已完成，可以查看输出结果和字幕预览。",
    failure: "任务执行失败，请查看错误信息和运行日志。",
  };

  const DEFAULT_SCENE = "日常对话";
  const RUNNING_STATES = new Set([
    "validating",
    "running_transcribe",
    "running_translate",
    "running_export",
  ]);

  const { STAGES, classifyLogLevel, getStageLabel, inferStatusFromMessage } = window.TaskProgress;
  const { TRANSLATION_MODES, validateTaskInput } = window.TaskValidation;
  const { buildPreviewModel } = window.PreviewModel;
  const { createInitialState, reduceState } = window.RendererState;

  function createEmptySettings() {
    return {
      model: "",
      baseUrl: "",
      apiKey: "",
    };
  }

  const elements = {
    appTitle: document.getElementById("app-title"),
    appSubtitle: document.getElementById("app-subtitle"),
    environmentBadge: document.getElementById("environment-badge"),
    openSettings: document.getElementById("open-settings"),
    openOutputTop: document.getElementById("open-output-top"),
    taskSummary: document.getElementById("task-summary"),
    pythonSummary: document.getElementById("python-summary"),
    outputSummary: document.getElementById("output-summary"),
    audioDropzone: document.getElementById("audio-dropzone"),
    browseAudio: document.getElementById("browse-audio"),
    audioName: document.getElementById("audio-name"),
    audioPath: document.getElementById("audio-path"),
    audioError: document.getElementById("audio-error"),
    modeSegmented: document.getElementById("mode-segmented"),
    sceneGroup: document.getElementById("scene-group"),
    sceneInput: document.getElementById("scene-input"),
    sceneError: document.getElementById("scene-error"),
    startTask: document.getElementById("start-task"),
    retryTask: document.getElementById("retry-task"),
    viewErrorDetail: document.getElementById("view-error-detail"),
    resetForm: document.getElementById("reset-form"),
    statusCaption: document.getElementById("status-caption"),
    stageStrip: document.getElementById("stage-strip"),
    currentStage: document.getElementById("current-stage"),
    elapsedTime: document.getElementById("elapsed-time"),
    latestMessage: document.getElementById("latest-message"),
    modelDownloadHint: document.getElementById("model-download-hint"),
    errorBanner: document.getElementById("error-banner"),
    autoScroll: document.getElementById("auto-scroll"),
    copyLogs: document.getElementById("copy-logs"),
    logList: document.getElementById("log-list"),
    resultEmpty: document.getElementById("result-empty"),
    resultContent: document.getElementById("result-content"),
    resultFileName: document.getElementById("result-file-name"),
    resultFilePath: document.getElementById("result-file-path"),
    openResultFile: document.getElementById("open-result-file"),
    openResultDir: document.getElementById("open-result-dir"),
    copyResultPath: document.getElementById("copy-result-path"),
    previewSummary: document.getElementById("preview-summary"),
    previewSearch: document.getElementById("preview-search"),
    previewList: document.getElementById("preview-list"),
    settingsModal: document.getElementById("settings-modal"),
    settingsDialog: document.getElementById("settings-dialog"),
    settingsClose: document.getElementById("settings-close"),
    settingsCancel: document.getElementById("settings-cancel"),
    settingsSave: document.getElementById("settings-save"),
    settingsLoading: document.getElementById("settings-loading"),
    settingsNextTaskHint: document.getElementById("settings-next-task-hint"),
    settingsTaskHint: document.getElementById("settings-task-hint"),
    settingsSuccess: document.getElementById("settings-success"),
    settingsError: document.getElementById("settings-error"),
    settingsModel: document.getElementById("settings-model"),
    settingsModelError: document.getElementById("settings-model-error"),
    settingsBaseUrl: document.getElementById("settings-base-url"),
    settingsBaseUrlError: document.getElementById("settings-base-url-error"),
    settingsApiKey: document.getElementById("settings-api-key"),
    settingsApiKeyHelp: document.getElementById("settings-api-key-help"),
    settingsToggleApiKey: document.getElementById("settings-toggle-api-key"),
  };

  const viewModel = {
    runtime: null,
    form: {
      audioPath: "",
      audioName: "",
      subtitleMode: "bilingual",
      scene: DEFAULT_SCENE,
    },
    taskState: createInitialState(),
    fieldErrors: {},
    logEntries: [],
    searchQuery: "",
    lastStageKey: "idle",
    lastErrorDetail: "",
    settings: {
      modalOpen: false,
      loading: false,
      saving: false,
      requestToken: 0,
      persisted: createEmptySettings(),
      draft: createEmptySettings(),
      fieldErrors: {
        model: "",
        baseUrl: "",
      },
      error: "",
      success: "",
      apiKeyVisible: false,
    },
  };

  function cloneSettings(settings) {
    return {
      model: String((settings && settings.model) || ""),
      baseUrl: String((settings && settings.baseUrl) || ""),
      apiKey: String((settings && settings.apiKey) || ""),
    };
  }

  function normalizeSettingsPayload(settings) {
    return {
      model: String((settings && settings.model) || "").trim(),
      baseUrl: String((settings && settings.baseUrl) || "").trim(),
      apiKey: String((settings && settings.apiKey) || "").trim(),
    };
  }

  function sanitizeLoadedSettings(settings) {
    return {
      model: String((settings && settings.model) || "").trim(),
      baseUrl: String((settings && settings.baseUrl) || "").trim(),
      apiKey: String((settings && settings.apiKey) || "").trim(),
    };
  }

  function nextSettingsToken() {
    viewModel.settings.requestToken += 1;
    return viewModel.settings.requestToken;
  }

  function isTranslationMode(mode) {
    return TRANSLATION_MODES.has(mode);
  }

  function isTaskRunning() {
    return RUNNING_STATES.has(viewModel.taskState.status);
  }

  function getActiveOutputDirectory() {
    if (viewModel.taskState.result && viewModel.taskState.result.output_dir) {
      return viewModel.taskState.result.output_dir;
    }
    return viewModel.runtime ? viewModel.runtime.outputDir : "";
  }

  function buildTaskSummary() {
    if (!viewModel.form.audioName) {
      return "未选择音频文件";
    }

    const parts = [viewModel.form.audioName, MODE_LABELS[viewModel.form.subtitleMode] || "字幕"];
    if (isTranslationMode(viewModel.form.subtitleMode) && viewModel.form.scene.trim()) {
      parts.push(viewModel.form.scene.trim());
    }
    return parts.join(" / ");
  }

  function formatDuration(startedAt) {
    if (!startedAt) {
      return "00:00";
    }
    const totalSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
    const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
    const seconds = String(totalSeconds % 60).padStart(2, "0");
    return `${minutes}:${seconds}`;
  }

  function formatTime(timestamp) {
    return new Date(timestamp).toLocaleTimeString("zh-CN", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  function createLogEntry(level, message, timestamp = Date.now()) {
    return {
      level,
      message: String(message || "").trim(),
      timestamp,
    };
  }

  function appendLog(message, level, timestamp) {
    const normalizedMessage = String(message || "").trim();
    if (!normalizedMessage) {
      return;
    }
    viewModel.logEntries.push(createLogEntry(level || classifyLogLevel(normalizedMessage), normalizedMessage, timestamp));
  }

  function clearLogs() {
    viewModel.logEntries = [];
  }

  function dispatchTaskEvent(event) {
    viewModel.taskState = reduceState(viewModel.taskState, event);
    if (event.type === "task/start") {
      viewModel.lastStageKey = "validating";
      viewModel.lastErrorDetail = "";
    } else if (event.type === "task/progress") {
      viewModel.lastStageKey = inferStatusFromMessage(event.message);
    } else if (event.type === "task/success") {
      viewModel.lastStageKey = "success";
    } else if (event.type === "task/reset") {
      viewModel.lastStageKey = "idle";
      viewModel.lastErrorDetail = "";
    }
  }

  function setFieldErrors(fieldErrors) {
    viewModel.fieldErrors = {
      audioPath: fieldErrors.audioPath || "",
      scene: fieldErrors.scene || "",
    };
  }

  function clearFieldError(fieldName) {
    if (viewModel.fieldErrors[fieldName]) {
      viewModel.fieldErrors[fieldName] = "";
    }
  }

  function setSettingsFieldErrors(fieldErrors) {
    viewModel.settings.fieldErrors = {
      model: fieldErrors.model || "",
      baseUrl: fieldErrors.baseUrl || "",
    };
  }

  function clearSettingsFieldError(fieldName) {
    if (viewModel.settings.fieldErrors[fieldName]) {
      viewModel.settings.fieldErrors[fieldName] = "";
    }
  }

  function resetSettingsDraft() {
    viewModel.settings.draft = cloneSettings(viewModel.settings.persisted);
    viewModel.settings.fieldErrors = {
      model: "",
      baseUrl: "",
    };
    viewModel.settings.error = "";
    viewModel.settings.success = "";
    viewModel.settings.apiKeyVisible = false;
  }

  function setAudioSelection(filePath, name) {
    viewModel.form.audioPath = String(filePath || "").trim();
    viewModel.form.audioName = String(name || fileNameFromPath(filePath) || "").trim();
    clearFieldError("audioPath");
    renderAll();
  }

  function fileNameFromPath(filePath) {
    const normalized = String(filePath || "").trim();
    if (!normalized) {
      return "";
    }
    const parts = normalized.split(/[\\/]/);
    return parts[parts.length - 1] || normalized;
  }

  function resetFormState() {
    viewModel.form = {
      audioPath: "",
      audioName: "",
      subtitleMode: "bilingual",
      scene: DEFAULT_SCENE,
    };
    viewModel.searchQuery = "";
    setFieldErrors({});
    clearLogs();
    dispatchTaskEvent({ type: "task/reset" });
    renderAll();
  }

  function getCurrentValidation() {
    return validateTaskInput({
      audioPath: viewModel.form.audioPath,
      subtitleMode: viewModel.form.subtitleMode,
      scene: viewModel.form.scene,
    });
  }

  function buildPayload() {
    const payload = {
      audio_path: viewModel.form.audioPath,
      subtitle_mode: viewModel.form.subtitleMode,
      gui_backend: "electron",
    };

    if (isTranslationMode(viewModel.form.subtitleMode)) {
      payload.scene = viewModel.form.scene.trim();
    }
    return payload;
  }

  function validateSettingsDraft() {
    const normalized = normalizeSettingsPayload(viewModel.settings.draft);
    const fieldErrors = {
      model: "",
      baseUrl: "",
    };

    if (!normalized.model) {
      fieldErrors.model = "请填写 LLM_MODEL。";
    }
    if (!normalized.baseUrl) {
      fieldErrors.baseUrl = "请填写 LLM_BASE_URL。";
    } else if (!/^https?:\/\//i.test(normalized.baseUrl)) {
      fieldErrors.baseUrl = "LLM_BASE_URL 必须以 http:// 或 https:// 开头。";
    }

    return {
      ok: !fieldErrors.model && !fieldErrors.baseUrl,
      fieldErrors,
      value: normalized,
    };
  }

  async function handleBrowseAudio() {
    if (isTaskRunning()) {
      return;
    }

    const selected = await window.appApi.selectAudioFile();
    if (!selected) {
      return;
    }
    setAudioSelection(selected.path, selected.name);
  }

  function extractDroppedFile(event) {
    const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
    if (!file) {
      return null;
    }

    const filePath = file.path || file.webkitRelativePath || "";
    if (!filePath) {
      return null;
    }

    return {
      path: filePath,
      name: file.name || fileNameFromPath(filePath),
    };
  }

  async function runTask() {
    if (isTaskRunning()) {
      return;
    }

    const validation = getCurrentValidation();
    setFieldErrors(validation.fieldErrors || {});
    if (!validation.ok) {
      appendLog("表单检查未通过，请先修正错误后再试。", "warning");
      renderAll();
      return;
    }

    clearLogs();
    dispatchTaskEvent({ type: "task/start" });
    appendLog("任务已提交，等待 Python 后端响应。", "info");
    renderAll();

    try {
      const result = await window.appApi.runSubtitleTask(buildPayload());
      dispatchTaskEvent({ type: "task/success", result });
      appendLog(`任务完成，已生成 ${fileNameFromPath(result.output_file)}。`, "info");
      renderAll();
      focusResultArea();
    } catch (error) {
      const normalizedError = error || {};
      const fieldErrors = normalizedError.fieldErrors || {};
      setFieldErrors(fieldErrors);
      viewModel.lastErrorDetail = String(
        normalizedError.stderrText || normalizedError.message || "任务执行失败。"
      ).trim();
      dispatchTaskEvent({
        type: "task/failure",
        errorMessage: normalizedError.message || "任务执行失败。",
      });

      const stderrLines = String(normalizedError.stderrText || "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);

      if (stderrLines.length > 0) {
        stderrLines.forEach((line) => appendLog(line, classifyLogLevel(line)));
      } else {
        appendLog(normalizedError.message || "任务执行失败。", "error");
      }

      renderAll();
    }
  }

  async function openSettingsModal() {
    const token = nextSettingsToken();
    viewModel.settings.modalOpen = true;
    viewModel.settings.loading = true;
    viewModel.settings.saving = false;
    resetSettingsDraft();
    renderSettings();

    try {
      const settings = sanitizeLoadedSettings(await window.appApi.getSettings());
      if (!viewModel.settings.modalOpen || token !== viewModel.settings.requestToken) {
        return;
      }
      viewModel.settings.persisted = settings;
      viewModel.settings.draft = cloneSettings(settings);
    } catch (error) {
      if (!viewModel.settings.modalOpen || token !== viewModel.settings.requestToken) {
        return;
      }
      viewModel.settings.error = String(error && error.message ? error.message : error || "读取设置失败。").trim();
    } finally {
      if (!viewModel.settings.modalOpen || token !== viewModel.settings.requestToken) {
        return;
      }
      viewModel.settings.loading = false;
      renderSettings();
      if (!viewModel.settings.error) {
        elements.settingsModel.focus();
      }
    }
  }

  function closeSettingsModal(options = {}) {
    const { focusTrigger = true } = options;
    if (!viewModel.settings.modalOpen || viewModel.settings.saving) {
      return;
    }

    nextSettingsToken();
    viewModel.settings.modalOpen = false;
    viewModel.settings.loading = false;
    resetSettingsDraft();
    renderSettings();

    if (focusTrigger && elements.openSettings) {
      elements.openSettings.focus();
    }
  }

  function updateSettingsField(fieldName, value) {
    if (!Object.prototype.hasOwnProperty.call(viewModel.settings.draft, fieldName)) {
      return;
    }

    viewModel.settings.draft[fieldName] = String(value || "");
    viewModel.settings.error = "";
    viewModel.settings.success = "";

    if (fieldName === "model") {
      clearSettingsFieldError("model");
    }
    if (fieldName === "baseUrl") {
      clearSettingsFieldError("baseUrl");
    }

    renderSettings();
  }

  function toggleSettingsApiKeyVisibility() {
    viewModel.settings.apiKeyVisible = !viewModel.settings.apiKeyVisible;
    renderSettings();
    elements.settingsApiKey.focus();
  }

  async function saveSettings() {
    if (!viewModel.settings.modalOpen || viewModel.settings.loading || viewModel.settings.saving) {
      return;
    }

    if (isTaskRunning()) {
      viewModel.settings.error = "任务运行中，暂时不能修改模型配置。";
      renderSettings();
      return;
    }

    const validation = validateSettingsDraft();
    setSettingsFieldErrors(validation.fieldErrors);
    viewModel.settings.error = "";
    viewModel.settings.success = "";

    if (!validation.ok) {
      renderSettings();
      return;
    }

    viewModel.settings.saving = true;
    renderSettings();

    try {
      const saved = normalizeSettingsPayload(await window.appApi.saveSettings(validation.value));
      viewModel.settings.persisted = saved;
      viewModel.settings.draft = cloneSettings(saved);
      viewModel.settings.success = "保存成功，新的模型配置会在下一次任务开始时生效。";
      appendLog("保存成功，新的模型配置会在下一次任务开始时生效。", "info");
      viewModel.settings.saving = false;
      closeSettingsModal();
      renderAll();
    } catch (error) {
      viewModel.settings.saving = false;
      viewModel.settings.error = String(error && error.message ? error.message : error || "保存设置失败。").trim();
      renderSettings();
    }
  }

  function focusResultArea() {
    if (!viewModel.taskState.result || !elements.resultContent) {
      return;
    }

    elements.resultContent.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  function renderEnvironment() {
    const runtime = viewModel.runtime || {};
    const environmentStatus = runtime.environmentStatus || {};

    elements.appTitle.textContent = runtime.appTitle || "音频字幕提取与翻译工具";
    elements.appSubtitle.textContent = runtime.appSubtitle || "";
    elements.taskSummary.textContent = buildTaskSummary();
    elements.pythonSummary.textContent = runtime.backendPython || "检测中...";
    elements.outputSummary.textContent = fileNameFromPath(getActiveOutputDirectory()) || getActiveOutputDirectory() || "output";

    elements.environmentBadge.textContent = environmentStatus.text || "环境待检查";
    elements.environmentBadge.classList.toggle("is-ready", environmentStatus.tone === "ready");
    elements.environmentBadge.classList.toggle("is-danger", environmentStatus.tone === "danger");
  }

  function renderForm() {
    const running = isTaskRunning();
    const hasAudio = Boolean(viewModel.form.audioPath);
    const showScene = isTranslationMode(viewModel.form.subtitleMode);
    const canRetry = hasAudio && !running;

    elements.audioName.textContent = viewModel.form.audioName || "拖入音频或点击浏览";
    elements.audioPath.textContent =
      viewModel.form.audioPath || "支持 mp3、wav、m4a、flac、aac";
    elements.audioError.textContent = viewModel.fieldErrors.audioPath || "";

    elements.audioDropzone.classList.toggle("is-disabled", running);
    elements.browseAudio.disabled = running;
    elements.browseAudio.textContent = running ? "任务进行中" : "浏览音频";

    Array.from(elements.modeSegmented.querySelectorAll("[data-mode]")).forEach((button) => {
      const mode = button.dataset.mode;
      button.classList.toggle("is-active", mode === viewModel.form.subtitleMode);
      button.disabled = running;
    });

    elements.sceneGroup.classList.toggle("hidden", !showScene);
    elements.sceneInput.disabled = running;
    elements.sceneInput.value = viewModel.form.scene;
    elements.sceneInput.classList.toggle("is-invalid", Boolean(viewModel.fieldErrors.scene));
    elements.sceneError.textContent = viewModel.fieldErrors.scene || "";

    elements.startTask.disabled = running;
    elements.startTask.textContent = running ? "任务执行中..." : "开始生成";

    elements.retryTask.disabled = !canRetry;
    elements.viewErrorDetail.classList.toggle("hidden", !viewModel.lastErrorDetail);
    elements.viewErrorDetail.disabled = !viewModel.lastErrorDetail;
    elements.resetForm.disabled = running;
  }

  function renderStageStrip() {
    const activeKey = viewModel.taskState.status === "success" ? "success" : viewModel.taskState.status;
    const lastWorkIndex = STAGES.findIndex((stage) => stage.key === viewModel.lastStageKey);
    const activeIndex = STAGES.findIndex((stage) => stage.key === activeKey);

    elements.stageStrip.innerHTML = "";

    STAGES.forEach((stage, index) => {
      const pill = document.createElement("div");
      pill.className = "stage-pill";
      pill.textContent = stage.label;

      if (viewModel.taskState.status === "success") {
        if (stage.key === "success" || (lastWorkIndex >= 0 && index <= lastWorkIndex && stage.key !== "idle")) {
          pill.classList.add(stage.key === "success" ? "is-success" : "is-active");
        }
      } else if (viewModel.taskState.status === "failure") {
        if (stage.key === "failure") {
          pill.classList.add("is-failure");
        } else if (lastWorkIndex >= 0 && index <= lastWorkIndex && stage.key !== "idle") {
          pill.classList.add("is-active");
        }
      } else if (activeIndex >= 0) {
        if (index === activeIndex) {
          pill.classList.add("is-active");
        } else if (index < activeIndex && stage.key !== "idle") {
          pill.classList.add("is-success");
        }
      }

      elements.stageStrip.appendChild(pill);
    });
  }

  function renderStatus() {
    const state = viewModel.taskState;
    const currentStageKey = state.status === "failure" ? "failure" : state.status === "success" ? "success" : viewModel.lastStageKey;
    const errorText = state.status === "failure" ? viewModel.lastErrorDetail || state.errorMessage : "";

    elements.statusCaption.textContent = STATUS_CAPTIONS[state.status] || STATUS_CAPTIONS.idle;
    elements.currentStage.textContent = getStageLabel(currentStageKey);
    elements.elapsedTime.textContent = formatDuration(state.startedAt);
    elements.latestMessage.textContent = state.latestMessage || "请选择音频文件后开始。";
    elements.modelDownloadHint.classList.toggle("hidden", !state.modelDownloadHint);
    elements.errorBanner.classList.toggle("hidden", !errorText);
    elements.errorBanner.textContent = errorText;
  }

  function renderLogs() {
    const logs = viewModel.logEntries;
    const shouldAutoScroll = Boolean(elements.autoScroll.checked);

    elements.copyLogs.disabled = logs.length === 0;

    if (logs.length === 0) {
      elements.logList.innerHTML = '<div class="log-empty">日志会在任务开始后实时显示在这里。</div>';
      return;
    }

    const fragment = document.createDocumentFragment();
    logs.forEach((entry) => {
      const row = document.createElement("div");
      row.className = `log-entry is-${entry.level}`;

      const level = document.createElement("div");
      level.className = "log-level";
      level.textContent = `${formatTime(entry.timestamp)} ${entry.level}`;

      const message = document.createElement("div");
      message.className = "log-message";
      message.textContent = entry.message;

      row.appendChild(level);
      row.appendChild(message);
      fragment.appendChild(row);
    });

    elements.logList.innerHTML = "";
    elements.logList.appendChild(fragment);

    if (shouldAutoScroll) {
      elements.logList.scrollTop = elements.logList.scrollHeight;
    }
  }

  function renderResult() {
    const result = viewModel.taskState.result;
    const hasResult = Boolean(result && result.output_file);

    elements.resultEmpty.classList.toggle("hidden", hasResult);
    elements.resultContent.classList.toggle("hidden", !hasResult);

    if (!hasResult) {
      elements.resultFileName.textContent = "--";
      elements.resultFilePath.textContent = "--";
      elements.openResultFile.disabled = true;
      elements.openResultDir.disabled = true;
      elements.copyResultPath.disabled = true;
      return;
    }

    elements.resultFileName.textContent = fileNameFromPath(result.output_file);
    elements.resultFilePath.textContent = result.output_file;
    elements.openResultFile.disabled = false;
    elements.openResultDir.disabled = false;
    elements.copyResultPath.disabled = false;
  }

  function renderPreview() {
    const result = viewModel.taskState.result;
    const previewText = result && result.preview_text ? result.preview_text : "";
    const subtitleMode = result && result.subtitle_mode ? result.subtitle_mode : viewModel.form.subtitleMode;

    elements.previewSearch.value = viewModel.searchQuery;

    if (!previewText) {
      elements.previewSummary.textContent = "生成字幕后，这里会显示可搜索的字幕预览。";
      elements.previewList.innerHTML = '<div class="preview-empty">生成字幕后，这里会显示可搜索的字幕预览。</div>';
      return;
    }

    const previewModel = buildPreviewModel({
      previewText,
      subtitleMode,
      searchQuery: viewModel.searchQuery,
    });

    if (viewModel.searchQuery.trim()) {
      elements.previewSummary.textContent = `共 ${previewModel.totalEntries} 条字幕，当前匹配 ${previewModel.entries.length} 条。`;
    } else {
      elements.previewSummary.textContent = `共 ${previewModel.totalEntries} 条字幕，可直接搜索内容。`;
    }

    if (previewModel.entries.length === 0) {
      elements.previewList.innerHTML = '<div class="preview-empty">没有匹配当前搜索词的字幕内容。</div>';
      return;
    }

    const fragment = document.createDocumentFragment();

    previewModel.entries.forEach((entry) => {
      const item = document.createElement("div");
      item.className = "preview-item";

      const header = document.createElement("div");
      header.className = "preview-item-header";

      const index = document.createElement("span");
      index.textContent = `#${entry.index}`;

      const timeRange = document.createElement("span");
      timeRange.textContent = entry.timeRange;

      header.appendChild(index);
      header.appendChild(timeRange);

      const body = document.createElement("div");
      body.className = "preview-item-body";

      const primary = document.createElement("div");
      primary.className = "preview-line";
      primary.textContent = entry.primaryText || "(空)";
      body.appendChild(primary);

      if (entry.secondaryText) {
        const secondary = document.createElement("div");
        secondary.className = "preview-line secondary";
        secondary.textContent = entry.secondaryText;
        body.appendChild(secondary);
      }

      item.appendChild(header);
      item.appendChild(body);
      fragment.appendChild(item);
    });

    elements.previewList.innerHTML = "";
    elements.previewList.appendChild(fragment);
  }

  function renderSettings() {
    const settings = viewModel.settings;
    const running = isTaskRunning();
    const inputDisabled = settings.loading || settings.saving;

    document.body.classList.toggle("modal-open", settings.modalOpen);
    elements.settingsModal.classList.toggle("hidden", !settings.modalOpen);
    elements.settingsModal.setAttribute("aria-hidden", settings.modalOpen ? "false" : "true");

    elements.settingsLoading.classList.toggle("hidden", !settings.loading);
    elements.settingsTaskHint.classList.toggle("hidden", !running);
    elements.settingsTaskHint.textContent = running ? "任务运行中，暂时不能修改模型配置。" : "";
    elements.settingsSuccess.classList.toggle("hidden", !settings.success);
    elements.settingsSuccess.textContent = settings.success;
    elements.settingsError.classList.toggle("hidden", !settings.error);
    elements.settingsError.textContent = settings.error;

    elements.settingsModel.value = settings.draft.model;
    elements.settingsBaseUrl.value = settings.draft.baseUrl;
    elements.settingsApiKey.value = settings.draft.apiKey;
    elements.settingsApiKey.type = settings.apiKeyVisible ? "text" : "password";
    elements.settingsToggleApiKey.textContent = settings.apiKeyVisible ? "隐藏" : "显示";
    elements.settingsApiKeyHelp.textContent = "可留空；留空会写入空值。";

    elements.settingsModel.disabled = inputDisabled;
    elements.settingsBaseUrl.disabled = inputDisabled;
    elements.settingsApiKey.disabled = inputDisabled;
    elements.settingsToggleApiKey.disabled = inputDisabled;
    elements.settingsSave.disabled = inputDisabled || running;

    elements.settingsModel.classList.toggle("is-invalid", Boolean(settings.fieldErrors.model));
    elements.settingsBaseUrl.classList.toggle("is-invalid", Boolean(settings.fieldErrors.baseUrl));
    elements.settingsModelError.textContent = settings.fieldErrors.model;
    elements.settingsBaseUrlError.textContent = settings.fieldErrors.baseUrl;
  }

  function renderAll() {
    renderEnvironment();
    renderForm();
    renderStageStrip();
    renderStatus();
    renderLogs();
    renderResult();
    renderPreview();
    renderSettings();
  }

  async function handleOpenOutputDirectory() {
    const outputDir = getActiveOutputDirectory();
    if (!outputDir) {
      appendLog("当前还没有可打开的输出目录。", "warning");
      renderAll();
      return;
    }

    await window.appApi.openOutputDirectory(outputDir);
  }

  async function handleCopyLogs() {
    if (viewModel.logEntries.length === 0) {
      return;
    }

    const text = viewModel.logEntries
      .map((entry) => `[${formatTime(entry.timestamp)}] ${entry.level.toUpperCase()} ${entry.message}`)
      .join("\n");

    await window.appApi.copyText(text);
    appendLog("运行日志已复制到剪贴板。", "info");
    renderAll();
  }

  async function handleOpenResultFile() {
    const result = viewModel.taskState.result;
    if (!result || !result.output_file) {
      return;
    }
    await window.appApi.openFile(result.output_file);
  }

  async function handleOpenResultDirectory() {
    const result = viewModel.taskState.result;
    if (!result || !result.output_dir) {
      return;
    }
    await window.appApi.openOutputDirectory(result.output_dir);
  }

  async function handleCopyResultPath() {
    const result = viewModel.taskState.result;
    if (!result || !result.output_file) {
      return;
    }

    await window.appApi.copyText(result.output_file);
    appendLog("结果文件路径已复制到剪贴板。", "info");
    renderAll();
  }

  function handleProgress(payload) {
    if (!payload || !payload.message) {
      return;
    }

    appendLog(payload.message, classifyLogLevel(payload.message), payload.timestamp || Date.now());
    dispatchTaskEvent({
      type: "task/progress",
      message: payload.message,
    });
    renderAll();
  }

  function bindEvents() {
    elements.openSettings.addEventListener("click", () => {
      if (!viewModel.settings.modalOpen) {
        openSettingsModal();
      }
    });

    elements.settingsClose.addEventListener("click", () => closeSettingsModal());
    elements.settingsCancel.addEventListener("click", () => closeSettingsModal());
    elements.settingsSave.addEventListener("click", () => {
      saveSettings();
    });
    elements.settingsToggleApiKey.addEventListener("click", () => {
      toggleSettingsApiKeyVisibility();
    });
    elements.settingsModal.addEventListener("click", (event) => {
      if (event.target === elements.settingsModal) {
        closeSettingsModal({ focusTrigger: false });
      }
    });

    elements.settingsModel.addEventListener("input", (event) => {
      updateSettingsField("model", event.target.value);
    });
    elements.settingsBaseUrl.addEventListener("input", (event) => {
      updateSettingsField("baseUrl", event.target.value);
    });
    elements.settingsApiKey.addEventListener("input", (event) => {
      updateSettingsField("apiKey", event.target.value);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && viewModel.settings.modalOpen) {
        event.preventDefault();
        closeSettingsModal();
      }
    });

    elements.openOutputTop.addEventListener("click", () => {
      handleOpenOutputDirectory();
    });

    elements.browseAudio.addEventListener("click", () => {
      handleBrowseAudio();
    });

    elements.audioDropzone.addEventListener("click", (event) => {
      if (isTaskRunning()) {
        event.preventDefault();
        return;
      }
      handleBrowseAudio();
    });

    elements.audioDropzone.addEventListener("dragover", (event) => {
      if (isTaskRunning()) {
        return;
      }
      event.preventDefault();
      elements.audioDropzone.classList.add("is-dragover");
    });

    elements.audioDropzone.addEventListener("dragleave", () => {
      elements.audioDropzone.classList.remove("is-dragover");
    });

    elements.audioDropzone.addEventListener("drop", (event) => {
      elements.audioDropzone.classList.remove("is-dragover");
      if (isTaskRunning()) {
        return;
      }

      event.preventDefault();
      const dropped = extractDroppedFile(event);
      if (dropped) {
        setAudioSelection(dropped.path, dropped.name);
      }
    });

    elements.sceneInput.addEventListener("input", (event) => {
      viewModel.form.scene = event.target.value;
      clearFieldError("scene");
      renderAll();
    });

    Array.from(elements.modeSegmented.querySelectorAll("[data-mode]")).forEach((button) => {
      button.addEventListener("click", () => {
        if (isTaskRunning()) {
          return;
        }

        viewModel.form.subtitleMode = button.dataset.mode;
        if (!isTranslationMode(viewModel.form.subtitleMode)) {
          viewModel.form.scene = DEFAULT_SCENE;
          clearFieldError("scene");
        }
        renderAll();
      });
    });

    elements.startTask.addEventListener("click", () => {
      runTask();
    });

    elements.retryTask.addEventListener("click", () => {
      runTask();
    });

    elements.viewErrorDetail.addEventListener("click", () => {
      if (!viewModel.lastErrorDetail) {
        return;
      }
      window.alert(viewModel.lastErrorDetail);
    });

    elements.resetForm.addEventListener("click", () => {
      resetFormState();
    });

    elements.copyLogs.addEventListener("click", () => {
      handleCopyLogs();
    });

    elements.openResultFile.addEventListener("click", () => {
      handleOpenResultFile();
    });

    elements.openResultDir.addEventListener("click", () => {
      handleOpenResultDirectory();
    });

    elements.copyResultPath.addEventListener("click", () => {
      handleCopyResultPath();
    });

    elements.previewSearch.addEventListener("input", (event) => {
      viewModel.searchQuery = event.target.value;
      renderPreview();
    });

    window.appApi.onTaskProgress((payload) => {
      handleProgress(payload);
    });
  }

  async function initialize() {
    try {
      viewModel.runtime = await window.appApi.getAppContext();
    } catch (error) {
      viewModel.runtime = {
        appTitle: "音频字幕提取与翻译工具",
        appSubtitle: "",
        outputDir: "",
        backendPython: "读取失败",
        environmentStatus: {
          tone: "danger",
          text: "运行环境信息读取失败",
        },
      };

      appendLog(String(error && error.message ? error.message : error || "读取运行环境失败。"), "error");
    }

    renderAll();
  }

  bindEvents();

  setInterval(() => {
    if (isTaskRunning()) {
      renderStatus();
    }
  }, 1000);

  initialize();
})();

