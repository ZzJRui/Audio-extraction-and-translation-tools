const fs = require("node:fs");
const path = require("node:path");

function getProjectRoot() {
  return path.resolve(__dirname, "..", "..", "..");
}

function getSiblingRuntimeRoot(projectRoot = getProjectRoot()) {
  return path.join(path.dirname(projectRoot), `${path.basename(projectRoot)}_runtime`);
}

function getDotRuntimeRoot(projectRoot = getProjectRoot()) {
  return path.join(projectRoot, ".runtime");
}

function normalizeOptionalPath(targetPath) {
  return String(targetPath || "").trim();
}

function buildExistingPathSet(existingPaths) {
  if (!Array.isArray(existingPaths) || existingPaths.length === 0) {
    return null;
  }

  return new Set(existingPaths.filter(Boolean).map((entry) => path.resolve(entry).toLowerCase()));
}

function pathExists(targetPath, existingPathSet = null) {
  if (!targetPath) {
    return false;
  }

  if (existingPathSet) {
    return existingPathSet.has(path.resolve(targetPath).toLowerCase());
  }

  return fs.existsSync(targetPath);
}

function resolveDevelopmentRuntimeRoot(options = {}) {
  const projectRoot = options.projectRoot || getProjectRoot();
  const explicitRuntimeRoot = normalizeOptionalPath(options.explicitRuntimeRoot ?? process.env.APP_RUNTIME_ROOT);
  const existingPathSet = buildExistingPathSet(options.existingPaths);
  const candidates = [
    getSiblingRuntimeRoot(projectRoot),
    explicitRuntimeRoot,
    getDotRuntimeRoot(projectRoot),
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (pathExists(candidate, existingPathSet)) {
      return path.resolve(candidate);
    }
  }

  return path.resolve(getSiblingRuntimeRoot(projectRoot));
}

function getBundleRoot(options = {}) {
  const projectRoot = options.projectRoot || getProjectRoot();
  const resourcesPath = options.resourcesPath || process.resourcesPath || "";
  const isPackaged = Boolean(options.isPackaged);

  if (isPackaged) {
    return path.join(resourcesPath, "runtime", "backend");
  }

  return path.resolve(projectRoot);
}

function getReadonlyRuntimeRoot(options = {}) {
  const projectRoot = options.projectRoot || getProjectRoot();
  const resourcesPath = options.resourcesPath || process.resourcesPath || "";
  const isPackaged = Boolean(options.isPackaged);

  if (isPackaged) {
    return path.join(resourcesPath, "runtime");
  }

  return resolveDevelopmentRuntimeRoot(options);
}

function getDataRoot(options = {}) {
  const projectRoot = options.projectRoot || getProjectRoot();
  const explicitDataRoot = normalizeOptionalPath(options.explicitDataRoot ?? process.env.APP_DATA_ROOT);
  const isPackaged = Boolean(options.isPackaged);
  const userDataPath = normalizeOptionalPath(options.userDataPath);

  if (explicitDataRoot) {
    return path.resolve(explicitDataRoot);
  }

  if (isPackaged && userDataPath) {
    return path.resolve(userDataPath);
  }

  return path.resolve(projectRoot);
}

function getWritableRuntimeRoot(options = {}) {
  const projectRoot = options.projectRoot || getProjectRoot();
  const explicitRuntimeRoot = normalizeOptionalPath(options.explicitRuntimeRoot ?? process.env.APP_RUNTIME_ROOT);
  const isPackaged = Boolean(options.isPackaged);

  if (isPackaged && explicitRuntimeRoot) {
    return path.resolve(explicitRuntimeRoot);
  }

  if (isPackaged) {
    return path.join(getDataRoot(options), "runtime");
  }

  return resolveDevelopmentRuntimeRoot({
    projectRoot,
    explicitRuntimeRoot,
    existingPaths: options.existingPaths,
  });
}

function getCacheRoot(options = {}) {
  return path.join(getWritableRuntimeRoot(options), "cache");
}

function getTempRoot(options = {}) {
  return path.join(getWritableRuntimeRoot(options), "temp");
}

function getDefaultOutputDir(options = {}) {
  return path.join(getDataRoot(options), "output");
}

function getLogsDir(options = {}) {
  return path.join(getDataRoot(options), "logs");
}

function getEnvFilePath(options = {}) {
  return path.join(getDataRoot(options), ".env");
}

function getEnvTemplatePath(options = {}) {
  return path.join(getBundleRoot(options), ".env.example");
}

module.exports = {
  getBundleRoot,
  getCacheRoot,
  getDataRoot,
  getDefaultOutputDir,
  getDotRuntimeRoot,
  getEnvFilePath,
  getEnvTemplatePath,
  getLogsDir,
  getProjectRoot,
  getReadonlyRuntimeRoot,
  getSiblingRuntimeRoot,
  getTempRoot,
  getWritableRuntimeRoot,
  resolveDevelopmentRuntimeRoot,
};
