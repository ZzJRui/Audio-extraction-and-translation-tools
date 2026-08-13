const fs = require("node:fs");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");

const { validateTaskInput } = require("../shared/validation");
const runtimePaths = require("./runtime-paths");

const PROGRESS_PREFIX = "__PROGRESS__:";

class BackendTaskError extends Error {
  constructor(message, options = {}) {
    super(message || "后端任务执行失败。");
    this.name = "BackendTaskError";
    this.stderrText = options.stderrText || "";
    this.exitCode = options.exitCode ?? null;
    this.fieldErrors = options.fieldErrors || {};
  }
}

function normalizePathOptions(options = {}) {
  const app = options.app || null;
  return {
    app,
    isPackaged: Boolean(options.isPackaged ?? (app && app.isPackaged)),
    userDataPath: options.userDataPath || (app && app.getPath ? app.getPath("userData") : ""),
    resourcesPath: options.resourcesPath || process.resourcesPath || "",
    projectRoot: options.projectRoot || runtimePaths.getProjectRoot(),
    explicitDataRoot: options.explicitDataRoot,
    explicitRuntimeRoot: options.explicitRuntimeRoot,
    existingPaths: options.existingPaths,
  };
}

function resolveRuntimeLocations(options = {}) {
  const pathOptions = normalizePathOptions(options);
  const bundleRoot = path.resolve(options.bundleRoot || runtimePaths.getBundleRoot(pathOptions));
  const dataRoot = path.resolve(options.dataRoot || runtimePaths.getDataRoot(pathOptions));
  const readonlyRuntimeRoot = path.resolve(
    options.readonlyRuntimeRoot || runtimePaths.getReadonlyRuntimeRoot(pathOptions)
  );
  const runtimeRoot = path.resolve(options.runtimeRoot || runtimePaths.getWritableRuntimeRoot(pathOptions));
  const cacheRoot = path.join(runtimeRoot, "cache");
  const tempRoot = path.join(runtimeRoot, "temp");
  const outputDir = path.join(dataRoot, "output");

  return {
    ...pathOptions,
    bundleRoot,
    cacheRoot,
    dataRoot,
    envFilePath: path.join(dataRoot, ".env"),
    envTemplatePath: path.join(bundleRoot, ".env.example"),
    outputDir,
    readonlyRuntimeRoot,
    runtimeRoot,
    tempRoot,
    backendScript: path.join(bundleRoot, "backend_runner.py"),
  };
}

function uniquePaths(paths) {
  const seen = new Set();
  const result = [];
  for (const entry of paths) {
    if (!entry) {
      continue;
    }
    const normalized = path.resolve(entry).toLowerCase();
    if (seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    result.push(path.resolve(entry));
  }
  return result;
}

function ensureDirectory(targetPath) {
  fs.mkdirSync(targetPath, { recursive: true });
}

function ensureRuntimeDirectories(locations) {
  [
    locations.dataRoot,
    locations.runtimeRoot,
    locations.cacheRoot,
    path.join(locations.cacheRoot, "huggingface"),
    locations.tempRoot,
    locations.outputDir,
  ].forEach(ensureDirectory);
}

function walkForFile(rootDir, targetFileName) {
  if (!rootDir || !fs.existsSync(rootDir)) {
    return null;
  }

  const queue = [rootDir];
  const expectedName = targetFileName.toLowerCase();
  while (queue.length > 0) {
    const currentDir = queue.shift();
    const entries = fs.readdirSync(currentDir, { withFileTypes: true });
    for (const entry of entries) {
      const entryPath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        queue.push(entryPath);
        continue;
      }
      if (entry.isFile() && entry.name.toLowerCase() === expectedName) {
        return entryPath;
      }
    }
  }

  return null;
}

function findBundledFfmpegBin(runtimeRoot, readonlyRuntimeRoot = runtimeRoot, bundleRoot = "") {
  const searchRoots = uniquePaths([
    path.join(runtimeRoot || "", "tools", "ffmpeg"),
    path.join(readonlyRuntimeRoot || "", "tools", "ffmpeg"),
    path.join(bundleRoot || "", "tools", "ffmpeg"),
  ]);

  for (const searchRoot of searchRoots) {
    const ffmpegPath = walkForFile(searchRoot, "ffmpeg.exe") || walkForFile(searchRoot, "ffmpeg");
    if (ffmpegPath) {
      return path.dirname(ffmpegPath);
    }
  }

  return null;
}

function getBundledPythonCandidatePaths(readonlyRuntimeRoot) {
  const pythonRoot = path.join(readonlyRuntimeRoot || "", "python");
  if (process.platform === "win32") {
    return [
      path.join(pythonRoot, "python.exe"),
      path.join(pythonRoot, "Scripts", "python.exe"),
    ];
  }

  return [
    path.join(pythonRoot, "bin", "python3"),
    path.join(pythonRoot, "bin", "python"),
  ];
}

function getBundledPythonPathEntries(readonlyRuntimeRoot) {
  const pythonRoot = path.join(readonlyRuntimeRoot || "", "python");
  if (process.platform === "win32") {
    return [
      pythonRoot,
      path.join(pythonRoot, "Scripts"),
      path.join(pythonRoot, "DLLs"),
      path.join(pythonRoot, "Library", "bin"),
    ];
  }

  return [
    path.join(pythonRoot, "bin"),
    path.join(pythonRoot, "lib"),
  ];
}

function getPythonCandidates(options = {}) {
  const locations = resolveRuntimeLocations(options);
  const candidates = [];
  const envPython = String(process.env.BACKEND_PYTHON || "").trim();

  if (envPython) {
    candidates.push({ command: envPython, args: [], source: "env" });
  }

  for (const bundledPath of getBundledPythonCandidatePaths(locations.readonlyRuntimeRoot)) {
    candidates.push({ command: bundledPath, args: [], source: "bundled" });
  }

  if (locations.isPackaged) {
    return candidates;
  }

  if (process.platform === "win32") {
    candidates.push({ command: "python", args: [], source: "system" });
    candidates.push({ command: "py", args: ["-3"], source: "system" });
  } else {
    candidates.push({ command: "python3", args: [], source: "system" });
    candidates.push({ command: "python", args: [], source: "system" });
  }

  return candidates;
}

function probeCommand(candidate) {
  const result = spawnSync(candidate.command, [...candidate.args, "--version"], {
    encoding: "utf8",
    windowsHide: true,
  });

  return !result.error && result.status === 0;
}

function resolvePythonLauncher(options = {}) {
  const locations = resolveRuntimeLocations(options);
  const candidates = getPythonCandidates(locations);
  for (const candidate of candidates) {
    if (probeCommand(candidate)) {
      return candidate;
    }
  }

  if (locations.isPackaged) {
    throw new BackendTaskError("应用运行时不完整，请重新安装应用。", {
      stderrText: `未找到可用的内置 Python 运行时。预期位置: ${getBundledPythonCandidatePaths(
        locations.readonlyRuntimeRoot
      ).join(" | ")}`,
    });
  }

  throw new BackendTaskError("没有找到可用的 Python 解释器。", {
    stderrText: "没有找到可用的 Python 解释器。请先安装 Python，或设置 BACKEND_PYTHON。",
  });
}

function getRuntimeSummary(options = {}) {
  const locations = resolveRuntimeLocations(options);
  try {
    const launcher = resolvePythonLauncher(locations);
    return {
      projectRoot: locations.projectRoot,
      bundleRoot: locations.bundleRoot,
      dataRoot: locations.dataRoot,
      envFilePath: locations.envFilePath,
      outputDir: locations.outputDir,
      backendPython: [launcher.command].concat(launcher.args).join(" "),
      environmentStatus: {
        tone: "ready",
        text: locations.isPackaged ? "内置运行时已就绪" : "Python 后端已就绪",
      },
    };
  } catch (error) {
    return {
      projectRoot: locations.projectRoot,
      bundleRoot: locations.bundleRoot,
      dataRoot: locations.dataRoot,
      envFilePath: locations.envFilePath,
      outputDir: locations.outputDir,
      backendPython: "未发现 Python",
      environmentStatus: {
        tone: "danger",
        text: locations.isPackaged ? "内置运行时缺失" : "Python 环境未就绪",
      },
    };
  }
}

function getPathKey(env = process.env) {
  return Object.keys(env).find((key) => key.toUpperCase() === "PATH") || "PATH";
}

function prependPathEntry(currentValue, entry) {
  if (!entry) {
    return currentValue || "";
  }

  const delimiter = path.delimiter;
  const entries = String(currentValue || "")
    .split(delimiter)
    .filter(Boolean);
  const normalizedEntry = process.platform === "win32" ? entry.toLowerCase() : entry;
  const hasEntry = entries.some((item) =>
    process.platform === "win32" ? item.toLowerCase() === normalizedEntry : item === normalizedEntry
  );

  if (hasEntry) {
    return entries.join(delimiter);
  }

  return [entry].concat(entries).join(delimiter);
}

function buildBackendEnv(options = {}) {
  const locations = resolveRuntimeLocations(options);
  ensureRuntimeDirectories(locations);

  const env = { ...process.env };
  const pathKey = getPathKey(env);
  const ffmpegBin = findBundledFfmpegBin(
    locations.runtimeRoot,
    locations.readonlyRuntimeRoot,
    locations.bundleRoot
  );
  const bundledPythonPathEntries = getBundledPythonPathEntries(locations.readonlyRuntimeRoot)
    .filter((entry) => fs.existsSync(entry));

  env.PYTHONUTF8 = "1";
  env.PYTHONIOENCODING = "utf-8";
  env.APP_BUNDLE_ROOT = locations.bundleRoot;
  env.APP_DATA_ROOT = locations.dataRoot;
  env.APP_RUNTIME_ROOT = locations.runtimeRoot;
  env.HF_HOME = path.join(locations.cacheRoot, "huggingface");
  env.XDG_CACHE_HOME = locations.cacheRoot;
  env.TEMP = locations.tempRoot;
  env.TMP = locations.tempRoot;

  if (bundledPythonPathEntries.length > 0) {
    env.PYTHONHOME = path.join(locations.readonlyRuntimeRoot, "python");
    for (const entry of bundledPythonPathEntries) {
      env[pathKey] = prependPathEntry(env[pathKey], entry);
    }
  }

  if (ffmpegBin) {
    env[pathKey] = prependPathEntry(env[pathKey], ffmpegBin);
  }

  return env;
}

function buildDisplayErrorMessage(stderrText) {
  const normalized = String(stderrText || "").trim();
  const lowered = normalized.toLowerCase();

  if (lowered.includes("ffmpeg")) {
    return "应用环境异常，请重新安装应用。";
  }
  if (lowered.includes("python") && lowered.includes("not found")) {
    return "应用运行时不完整，请重新安装应用。";
  }

  return normalized || "后端任务执行失败。";
}

function runBackendTask({ command, args = [], cwd, env, payload, onProgress }) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });

    let stdoutText = "";
    let stderrBuffer = "";
    const stderrLines = [];

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");

    child.stdout.on("data", (chunk) => {
      stdoutText += chunk;
    });

    child.stderr.on("data", (chunk) => {
      stderrBuffer += String(chunk);
      const parts = stderrBuffer.split(/\r?\n/);
      stderrBuffer = parts.pop() || "";

      for (const line of parts) {
        const trimmed = line.trim();
        if (!trimmed) {
          continue;
        }
        if (trimmed.startsWith(PROGRESS_PREFIX)) {
          if (typeof onProgress === "function") {
            onProgress(trimmed.slice(PROGRESS_PREFIX.length).trim());
          }
          continue;
        }
        stderrLines.push(trimmed);
      }
    });

    child.on("error", (error) => {
      reject(new BackendTaskError(error.message, { stderrText: error.message }));
    });

    child.on("close", (code) => {
      if (stderrBuffer.trim()) {
        stderrLines.push(stderrBuffer.trim());
      }

      const stderrText = stderrLines.join("\n").trim();
      if (code !== 0) {
        reject(
          new BackendTaskError(buildDisplayErrorMessage(stderrText), {
            stderrText,
            exitCode: code,
          })
        );
        return;
      }

      const normalizedStdout = stdoutText.trim();
      if (!normalizedStdout) {
        reject(new BackendTaskError("后端未返回结果。", { stderrText, exitCode: code }));
        return;
      }

      try {
        resolve(JSON.parse(normalizedStdout));
      } catch (error) {
        reject(
          new BackendTaskError("后端返回了无法解析的结果。", {
            stderrText: `${stderrText}\n${error.message}`.trim(),
            exitCode: code,
          })
        );
      }
    });

    child.stdin.write(JSON.stringify(payload || {}));
    child.stdin.end();
  });
}

async function runPythonSubtitleTask({ payload, onProgress, ...options }) {
  const validation = validateTaskInput({
    audioPath: payload.audio_path,
    subtitleMode: payload.subtitle_mode,
    scene: payload.scene,
  });

  if (!validation.ok) {
    throw new BackendTaskError("提交参数未通过检查。", {
      stderrText: "请先修正表单中的错误后再试。",
      fieldErrors: validation.fieldErrors,
    });
  }

  const locations = resolveRuntimeLocations(options);
  const launcher = resolvePythonLauncher(locations);
  const backendScript = locations.backendScript;
  if (!fs.existsSync(backendScript)) {
    throw new BackendTaskError("应用运行时不完整，请重新安装应用。", {
      stderrText: `后端脚本不存在: ${backendScript}`,
    });
  }

  const env = buildBackendEnv(locations);
  env.BACKEND_PYTHON = launcher.command;

  return runBackendTask({
    command: launcher.command,
    args: launcher.args.concat([backendScript]),
    cwd: locations.bundleRoot,
    env,
    payload,
    onProgress,
  });
}

module.exports = {
  BackendTaskError,
  PROGRESS_PREFIX,
  buildBackendEnv,
  findBundledFfmpegBin,
  getRuntimeSummary,
  resolvePythonLauncher,
  resolveRuntimeLocations,
  runBackendTask,
  runPythonSubtitleTask,
};

