const fs = require("node:fs/promises");
const path = require("node:path");
const { app, BrowserWindow, clipboard, dialog, ipcMain, shell } = require("electron");

const runtimePaths = require("./runtime-paths");
const { BackendTaskError, getRuntimeSummary, runPythonSubtitleTask } = require("./python-task");

const APP_TITLE = "音频字幕提取与翻译工具";
const APP_SUBTITLE = "支持生成原文、译文或双语字幕，适合边看日志边校对成品。";
const AUDIO_FILTERS = [
  { name: "音频文件", extensions: ["mp3", "wav", "m4a", "flac", "aac"] },
  { name: "所有文件", extensions: ["*"] },
];
const SETTINGS_KEYS = ["LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY"];
const SETTINGS_KEY_SET = new Set(SETTINGS_KEYS);

let mainWindow = null;
let activeTask = null;

function getPathOptions() {
  return {
    app,
    isPackaged: app.isPackaged,
    projectRoot: runtimePaths.getProjectRoot(),
    resourcesPath: process.resourcesPath,
    userDataPath: app.getPath("userData"),
  };
}

function getSettingsPaths() {
  const options = getPathOptions();
  return {
    dataRoot: runtimePaths.getDataRoot(options),
    envFilePath: runtimePaths.getEnvFilePath(options),
    envTemplatePath: runtimePaths.getEnvTemplatePath(options),
    outputDir: runtimePaths.getDefaultOutputDir(options),
  };
}

async function ensureWritableEnvFile() {
  const { dataRoot, envFilePath, envTemplatePath, outputDir } = getSettingsPaths();
  await fs.mkdir(dataRoot, { recursive: true });
  await fs.mkdir(outputDir, { recursive: true });

  try {
    await fs.access(envFilePath);
    return envFilePath;
  } catch (error) {
    if (!error || error.code !== "ENOENT") {
      throw error;
    }
  }

  try {
    await fs.copyFile(envTemplatePath, envFilePath);
  } catch (error) {
    if (!error || error.code !== "ENOENT") {
      throw error;
    }
    await fs.writeFile(envFilePath, "", "utf8");
  }

  return envFilePath;
}

function createEmptySettings() {
  return {
    model: "",
    baseUrl: "",
    apiKey: "",
  };
}

function stripWrappingQuotes(value) {
  const normalized = String(value || "").trim();
  if (
    normalized.length >= 2 &&
    ((normalized.startsWith('"') && normalized.endsWith('"')) ||
      (normalized.startsWith("'") && normalized.endsWith("'")))
  ) {
    return normalized.slice(1, -1);
  }
  return normalized;
}

function getSettingValueByKey(key, settings) {
  if (key === "LLM_MODEL") {
    return settings.model;
  }
  if (key === "LLM_BASE_URL") {
    return settings.baseUrl;
  }
  if (key === "LLM_API_KEY") {
    return settings.apiKey;
  }
  return "";
}

function readSettingsFromEnvText(envText) {
  const settings = createEmptySettings();
  const normalizedText = String(envText || "").replace(/^\uFEFF/, "");

  for (const line of normalizedText.split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
    if (!match) {
      continue;
    }

    const [, key, rawValue] = match;
    if (!SETTINGS_KEY_SET.has(key)) {
      continue;
    }

    const normalizedValue = stripWrappingQuotes(rawValue);
    if (key === "LLM_MODEL") {
      settings.model = normalizedValue;
    } else if (key === "LLM_BASE_URL") {
      settings.baseUrl = normalizedValue;
    } else if (key === "LLM_API_KEY") {
      settings.apiKey = normalizedValue;
    }
  }

  return settings;
}

async function loadSettingsFromEnvFile() {
  const envFilePath = await ensureWritableEnvFile();
  const envText = await fs.readFile(envFilePath, "utf8");
  return readSettingsFromEnvText(envText);
}

function normalizeSettingsPayload(payload) {
  const source = payload && typeof payload === "object" ? payload : {};
  const normalized = {
    model: String(source.model || "").trim(),
    baseUrl: String(source.baseUrl || "").trim(),
    apiKey: String(source.apiKey || "").trim(),
  };

  if (!normalized.model) {
    throw new Error("LLM_MODEL 不能为空。");
  }
  if (!normalized.baseUrl) {
    throw new Error("LLM_BASE_URL 不能为空。");
  }
  if (!/^https?:\/\//i.test(normalized.baseUrl)) {
    throw new Error("LLM_BASE_URL 必须以 http:// 或 https:// 开头。");
  }

  return normalized;
}

async function saveSettingsToEnvFile(payload) {
  const settings = normalizeSettingsPayload(payload);
  const envFilePath = await ensureWritableEnvFile();
  const originalText = await fs.readFile(envFilePath, "utf8");
  const newline = originalText.includes("\r\n") ? "\r\n" : "\n";
  const lines = originalText ? originalText.split(/\r?\n/) : [];
  const foundKeys = new Set();
  const updatedLines = lines.map((line) => {
    const match = line.match(/^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$/);
    if (!match) {
      return line;
    }

    const [, leadingWhitespace, key, separator] = match;
    if (!SETTINGS_KEY_SET.has(key)) {
      return line;
    }

    foundKeys.add(key);
    return `${leadingWhitespace}${key}${separator}${getSettingValueByKey(key, settings)}`;
  });

  for (const key of SETTINGS_KEYS) {
    if (!foundKeys.has(key)) {
      updatedLines.push(`${key}=${getSettingValueByKey(key, settings)}`);
    }
  }

  await fs.writeFile(envFilePath, updatedLines.join(newline).trimEnd() + newline, "utf8");
  return settings;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 860,
    minWidth: 1240,
    minHeight: 760,
    backgroundColor: "#14181d",
    title: APP_TITLE,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "..", "renderer", "index.html"));
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function serializeError(error) {
  if (error && typeof error === "object") {
    return {
      message: error.message || "任务执行失败。",
      stderrText: error.stderrText || "",
      exitCode: error.exitCode ?? null,
      fieldErrors: error.fieldErrors || {},
      name: error.name || "Error",
    };
  }

  return {
    message: String(error || "任务执行失败。"),
    stderrText: "",
    exitCode: null,
    fieldErrors: {},
    name: "Error",
  };
}

ipcMain.handle("app:get-context", async () => {
  await ensureWritableEnvFile();
  const summary = getRuntimeSummary(getPathOptions());
  return {
    appTitle: APP_TITLE,
    appSubtitle: APP_SUBTITLE,
    projectRoot: summary.projectRoot,
    bundleRoot: summary.bundleRoot,
    dataRoot: summary.dataRoot,
    envFilePath: summary.envFilePath,
    outputDir: summary.outputDir,
    environmentStatus: summary.environmentStatus,
    backendPython: summary.backendPython,
  };
});

ipcMain.handle("dialog:select-audio-file", async () => {
  const result = await dialog.showOpenDialog({
    title: "选择音频文件",
    properties: ["openFile"],
    filters: AUDIO_FILTERS,
  });

  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }

  const filePath = result.filePaths[0];
  return {
    path: filePath,
    name: path.basename(filePath),
  };
});

ipcMain.handle("task:run", async (event, payload) => {
  if (activeTask) {
    return {
      ok: false,
      error: serializeError(
        new BackendTaskError("当前任务仍在执行，请等待完成后再试。", {
          stderrText: "当前任务仍在执行，请等待完成后再试。",
        })
      ),
    };
  }

  activeTask = { startedAt: Date.now() };
  try {
    const result = await runPythonSubtitleTask({
      payload,
      ...getPathOptions(),
      onProgress(message) {
        event.sender.send("task:progress", {
          message,
          timestamp: Date.now(),
        });
      },
    });

    return { ok: true, data: result };
  } catch (error) {
    return { ok: false, error: serializeError(error) };
  } finally {
    activeTask = null;
  }
});

ipcMain.handle("shell:open-output-directory", async (_event, targetPath) => shell.openPath(targetPath));
ipcMain.handle("shell:open-file", async (_event, targetPath) => shell.openPath(targetPath));
ipcMain.handle("clipboard:copy", async (_event, text) => {
  clipboard.writeText(String(text || ""));
  return true;
});
ipcMain.handle("settings:get", async () => loadSettingsFromEnvFile());
ipcMain.handle("settings:save", async (_event, payload) => {
  if (activeTask) {
    throw new Error("当前任务正在运行，完成后才能保存设置。");
  }
  return saveSettingsToEnvFile(payload);
});

app.whenReady().then(async () => {
  await ensureWritableEnvFile();
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
