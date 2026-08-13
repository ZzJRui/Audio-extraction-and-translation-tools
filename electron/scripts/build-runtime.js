const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const APP_ROOT = path.resolve(__dirname, "..", "..");
const RUNTIME_BUILD_ROOT = path.join(APP_ROOT, ".runtime-build");
const BACKEND_DEST = path.join(RUNTIME_BUILD_ROOT, "backend");
const PYTHON_DEST = path.join(RUNTIME_BUILD_ROOT, "python");
const TOOLS_DEST = path.join(RUNTIME_BUILD_ROOT, "tools");
const FFMPEG_DEST = path.join(TOOLS_DEST, "ffmpeg");
const RUNTIME_REQUIREMENTS_FILE = path.join(APP_ROOT, "requirements-runtime.txt");
const REQUIREMENTS_FILE = fs.existsSync(RUNTIME_REQUIREMENTS_FILE)
  ? RUNTIME_REQUIREMENTS_FILE
  : path.join(APP_ROOT, "requirements.txt");
const BACKEND_RESOURCE_NAMES = [".env.example", "requirements.txt"];
const PORTABLE_PYTHON_DIR_NAMES = ["DLLs", "Lib"];
const PORTABLE_PYTHON_FILE_PATTERNS = [
  /^api-ms-win-.*\.dll$/i,
  /^concrt.*\.dll$/i,
  /^msvcp.*\.dll$/i,
  /^python.*\.dll$/i,
  /^python.*\.exe$/i,
  /^ucrtbase\.dll$/i,
  /^vcomp.*\.dll$/i,
  /^vcruntime.*\.dll$/i,
  /^zlib.*\.dll$/i,
];
const PORTABLE_PYTHON_LIBRARY_BIN_FILES = [
  "ffi.dll",
  "libbz2.dll",
  "libcrypto-3-x64.dll",
  "liblzma.dll",
  "libssl-3-x64.dll",
  "sqlite3.dll",
];
const SKIP_SEARCH_DIR_NAMES = new Set([
  ".git",
  ".runtime-build",
  ".tmp_test",
  "dist",
  "node_modules",
  "__pycache__",
]);
const EXCLUDED_STDLIB_DIR_NAMES = new Set(["ensurepip", "idlelib", "test", "tkinter", "turtledemo"]);

function log(message) {
  process.stdout.write(`${message}\n`);
}

function ensureCleanDirectory(targetPath) {
  fs.rmSync(targetPath, { recursive: true, force: true });
  fs.mkdirSync(targetPath, { recursive: true });
}

function ensureDirectory(targetPath) {
  fs.mkdirSync(targetPath, { recursive: true });
}

function copyDirectory(sourceDir, targetDir) {
  fs.cpSync(sourceDir, targetDir, { recursive: true, force: true });
}

function copyDirectoryFiltered(sourceDir, targetDir, filter) {
  fs.cpSync(sourceDir, targetDir, {
    recursive: true,
    force: true,
    filter: filter
      ? (entryPath) => filter(path.resolve(entryPath))
      : undefined,
  });
}

function copyFile(sourcePath, targetPath) {
  ensureDirectory(path.dirname(targetPath));
  fs.copyFileSync(sourcePath, targetPath);
}

function listBackendPythonFiles() {
  return fs
    .readdirSync(APP_ROOT, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".py"))
    .map((entry) => entry.name)
    .sort((left, right) => left.localeCompare(right, "zh-CN"));
}

function copyBackendResources() {
  ensureDirectory(BACKEND_DEST);

  for (const name of listBackendPythonFiles().concat(BACKEND_RESOURCE_NAMES)) {
    const sourcePath = path.join(APP_ROOT, name);
    if (!fs.existsSync(sourcePath)) {
      continue;
    }
    copyFile(sourcePath, path.join(BACKEND_DEST, name));
  }
}

function runCommand(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd || APP_ROOT,
    env: options.env || process.env,
    stdio: options.stdio || "inherit",
    windowsHide: true,
    encoding: options.encoding,
  });

  if (result.error) {
    throw result.error;
  }

  if (typeof result.status === "number" && result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} exited with code ${result.status}`);
  }

  return result;
}

function probePython(command, args = []) {
  const result = spawnSync(command, [...args, "--version"], {
    cwd: APP_ROOT,
    stdio: "pipe",
    windowsHide: true,
    encoding: "utf8",
  });

  return !result.error && result.status === 0;
}

function resolvePythonBuilder() {
  const explicitPython = String(process.env.BUILD_RUNTIME_PYTHON || "").trim();
  if (explicitPython && probePython(explicitPython)) {
    return { command: explicitPython, args: [], source: "BUILD_RUNTIME_PYTHON" };
  }

  const candidates = process.platform === "win32"
    ? [
        { command: "py", args: ["-3.13"], source: "py -3.13" },
        { command: "python", args: [], source: "python" },
      ]
    : [
        { command: "python3.13", args: [], source: "python3.13" },
        { command: "python3", args: [], source: "python3" },
      ];

  for (const candidate of candidates) {
    if (probePython(candidate.command, candidate.args)) {
      return candidate;
    }
  }

  throw new Error("未找到可用于构建运行时的 Python 3.13。请先安装 Python 3.13，或设置 BUILD_RUNTIME_PYTHON。");
}

function getBundledPythonExecutable(runtimeRoot = PYTHON_DEST) {
  return process.platform === "win32"
    ? path.join(runtimeRoot, "python.exe")
    : path.join(runtimeRoot, "bin", "python3");
}

function buildPipEnv() {
  const nextEnv = { ...process.env };
  delete nextEnv.PYTHONHOME;
  delete nextEnv.PYTHONPATH;
  nextEnv.PYTHONUTF8 = "1";
  nextEnv.PYTHONIOENCODING = "utf-8";
  return nextEnv;
}

function readPythonRuntimeInfo(builder) {
  const result = runCommand(
    builder.command,
    builder.args.concat([
      "-c",
      "import json, sys; print(json.dumps({'executable': sys.executable, 'prefix': sys.prefix, 'base_prefix': sys.base_prefix, 'version': sys.version.split()[0]}, ensure_ascii=False))",
    ]),
    {
      env: buildPipEnv(),
      stdio: "pipe",
      encoding: "utf8",
    }
  );

  try {
    return JSON.parse(String(result.stdout || "").trim());
  } catch (error) {
    throw new Error(`无法解析 Python 构建器信息: ${error.message}`);
  }
}

function shouldCopyPortablePythonEntry(entryPath, portablePrefix) {
  const normalizedPath = path.resolve(entryPath);
  const relativePath = path.relative(portablePrefix, normalizedPath);
  if (!relativePath || relativePath === ".") {
    return true;
  }

  const segments = relativePath.split(path.sep);
  if (segments.some((segment) => SKIP_SEARCH_DIR_NAMES.has(segment))) {
    return false;
  }

  if (segments.includes("__pycache__")) {
    return false;
  }

  if (segments[0] === "Lib" && segments[1] === "site-packages") {
    return false;
  }

  if (segments[0] === "Lib" && EXCLUDED_STDLIB_DIR_NAMES.has(segments[1])) {
    return false;
  }

  return true;
}

function copyPortablePythonCore(portablePrefix) {
  ensureDirectory(PYTHON_DEST);

  for (const dirName of PORTABLE_PYTHON_DIR_NAMES) {
    const sourceDir = path.join(portablePrefix, dirName);
    if (!fs.existsSync(sourceDir)) {
      continue;
    }
    copyDirectoryFiltered(sourceDir, path.join(PYTHON_DEST, dirName), (entryPath) =>
      shouldCopyPortablePythonEntry(entryPath, portablePrefix)
    );
  }

  const rootEntries = fs.readdirSync(portablePrefix, { withFileTypes: true });
  for (const entry of rootEntries) {
    if (!entry.isFile()) {
      continue;
    }

    if (!PORTABLE_PYTHON_FILE_PATTERNS.some((pattern) => pattern.test(entry.name))) {
      continue;
    }

    copyFile(path.join(portablePrefix, entry.name), path.join(PYTHON_DEST, entry.name));
  }

  const libraryBinSource = path.join(portablePrefix, "Library", "bin");
  const libraryBinDest = path.join(PYTHON_DEST, "Library", "bin");
  for (const fileName of PORTABLE_PYTHON_LIBRARY_BIN_FILES) {
    const sourcePath = path.join(libraryBinSource, fileName);
    if (!fs.existsSync(sourcePath)) {
      throw new Error(`构建内置 Python 时缺少必要 DLL: ${sourcePath}`);
    }
    copyFile(sourcePath, path.join(libraryBinDest, fileName));
  }
}

function installBundledPythonDependencies(builder) {
  const sitePackagesDir = path.join(PYTHON_DEST, "Lib", "site-packages");
  ensureDirectory(sitePackagesDir);
  runCommand(
    builder.command,
    builder.args.concat([
      "-m",
      "pip",
      "install",
      "-r",
      REQUIREMENTS_FILE,
      "--target",
      sitePackagesDir,
      "--no-warn-script-location",
    ]),
    {
      env: buildPipEnv(),
    }
  );
}

function createPortablePythonMetadata(runtimeInfo) {
  const metadataPath = path.join(PYTHON_DEST, "runtime.json");
  const metadata = {
    generatedAt: new Date().toISOString(),
    sourceExecutable: runtimeInfo.executable,
    sourcePrefix: runtimeInfo.prefix,
    pythonVersion: runtimeInfo.version,
  };
  fs.writeFileSync(metadataPath, `${JSON.stringify(metadata, null, 2)}\n`, "utf8");
}

function createBundledPythonRuntime() {
  const builder = resolvePythonBuilder();
  const runtimeInfo = readPythonRuntimeInfo(builder);
  log(`[build:runtime] 使用 Python 构建器: ${builder.source}`);
  log(`[build:runtime] Python 前缀目录: ${runtimeInfo.prefix}`);

  copyPortablePythonCore(runtimeInfo.prefix);
  installBundledPythonDependencies(builder);

  const bundledPython = getBundledPythonExecutable(PYTHON_DEST);
  if (!fs.existsSync(bundledPython)) {
    throw new Error(`内置 Python 未生成成功: ${bundledPython}`);
  }

  const probeResult = spawnSync(bundledPython, ["--version"], {
    cwd: APP_ROOT,
    env: buildPipEnv(),
    stdio: "pipe",
    windowsHide: true,
    encoding: "utf8",
  });
  if (probeResult.error || probeResult.status !== 0) {
    const stderrText = String(probeResult.stderr || probeResult.error || "").trim();
    throw new Error(`内置 Python 启动失败: ${stderrText || "未知错误"}`);
  }

  createPortablePythonMetadata(runtimeInfo);

  return {
    builder,
    executable: bundledPython,
    runtimeInfo,
  };
}

function hasFfmpegExecutable(searchRoot) {
  if (!searchRoot || !fs.existsSync(searchRoot)) {
    return false;
  }

  const queue = [searchRoot];
  while (queue.length > 0) {
    const currentDir = queue.shift();
    const entries = fs.readdirSync(currentDir, { withFileTypes: true });
    for (const entry of entries) {
      const entryPath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        queue.push(entryPath);
        continue;
      }
      if (entry.isFile() && ["ffmpeg.exe", "ffmpeg"].includes(entry.name.toLowerCase())) {
        return true;
      }
    }
  }

  return false;
}

function getFfmpegContainerRoot(ffmpegExecutablePath) {
  let currentPath = path.dirname(ffmpegExecutablePath);
  while (currentPath && currentPath !== path.dirname(currentPath)) {
    if (path.basename(currentPath).toLowerCase() === "ffmpeg") {
      return currentPath;
    }
    currentPath = path.dirname(currentPath);
  }
  return path.dirname(ffmpegExecutablePath);
}

function findFfmpegExecutable(rootDir) {
  if (!rootDir || !fs.existsSync(rootDir)) {
    return null;
  }

  const queue = [rootDir];
  while (queue.length > 0) {
    const currentDir = queue.shift();
    const entries = fs.readdirSync(currentDir, { withFileTypes: true });
    for (const entry of entries) {
      const entryPath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        if (SKIP_SEARCH_DIR_NAMES.has(entry.name)) {
          continue;
        }
        queue.push(entryPath);
        continue;
      }
      if (entry.isFile() && ["ffmpeg.exe", "ffmpeg"].includes(entry.name.toLowerCase())) {
        return entryPath;
      }
    }
  }

  return null;
}

function resolveFfmpegSourceRoot() {
  const explicitRoots = [
    process.env.FFMPEG_ROOT,
    process.env.FFMPEG_HOME,
    process.env.FFMPEG_DIR,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);

  for (const explicitRoot of explicitRoots) {
    if (hasFfmpegExecutable(explicitRoot)) {
      return path.resolve(explicitRoot);
    }
  }

  const explicitExecutable = String(process.env.FFMPEG_BIN || "").trim();
  if (explicitExecutable && fs.existsSync(explicitExecutable)) {
    return getFfmpegContainerRoot(path.resolve(explicitExecutable));
  }

  const commonRoots = [
    path.join(APP_ROOT, "tools", "ffmpeg"),
    path.join(APP_ROOT, ".runtime", "tools", "ffmpeg"),
    path.join(APP_ROOT, "runtime", "tools", "ffmpeg"),
  ];

  for (const candidate of commonRoots) {
    if (hasFfmpegExecutable(candidate)) {
      return path.resolve(candidate);
    }
  }

  const discoveredExecutable = findFfmpegExecutable(APP_ROOT);
  if (discoveredExecutable) {
    return getFfmpegContainerRoot(path.resolve(discoveredExecutable));
  }

  throw new Error("未在项目内找到 ffmpeg 运行时。请先将 ffmpeg 解压到 tools/ffmpeg，或设置 FFMPEG_ROOT / FFMPEG_BIN。");
}

function copyBundledFfmpeg() {
  const ffmpegSourceRoot = resolveFfmpegSourceRoot();
  copyDirectory(ffmpegSourceRoot, FFMPEG_DEST);
  return ffmpegSourceRoot;
}

function writeBuildManifest(context) {
  const manifestPath = path.join(RUNTIME_BUILD_ROOT, "build-manifest.json");
  const manifest = {
    generatedAt: new Date().toISOString(),
    backendFiles: listBackendPythonFiles(),
    ffmpegSourceRoot: context.ffmpegSourceRoot,
    pythonBuilder: context.pythonBuilder,
    bundledPython: context.bundledPython,
    pythonRuntimeInfo: context.pythonRuntimeInfo,
    requirementsFile: REQUIREMENTS_FILE,
  };
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
}

function buildRuntime() {
  ensureCleanDirectory(RUNTIME_BUILD_ROOT);
  copyBackendResources();
  const pythonRuntime = createBundledPythonRuntime();
  const ffmpegSourceRoot = copyBundledFfmpeg();
  writeBuildManifest({
    ffmpegSourceRoot,
    pythonBuilder: pythonRuntime.builder,
    bundledPython: pythonRuntime.executable,
    pythonRuntimeInfo: pythonRuntime.runtimeInfo,
  });

  log("[build:runtime] 运行时组装完成");
  log(`[build:runtime] backend -> ${BACKEND_DEST}`);
  log(`[build:runtime] python  -> ${PYTHON_DEST}`);
  log(`[build:runtime] ffmpeg  -> ${FFMPEG_DEST}`);
}

if (require.main === module) {
  try {
    buildRuntime();
  } catch (error) {
    console.error(`[build:runtime] ${error && error.message ? error.message : String(error)}`);
    process.exit(1);
  }
}

module.exports = {
  APP_ROOT,
  BACKEND_DEST,
  FFMPEG_DEST,
  PYTHON_DEST,
  RUNTIME_BUILD_ROOT,
  buildRuntime,
  copyBackendResources,
  createBundledPythonRuntime,
  resolveFfmpegSourceRoot,
  resolvePythonBuilder,
};
