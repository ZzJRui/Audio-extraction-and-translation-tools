const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { buildBackendEnv, findBundledFfmpegBin } = require("../src/main/python-task");

function makeTempDir() {
  const baseDir = path.join(process.cwd(), ".tmp_test");
  fs.mkdirSync(baseDir, { recursive: true });
  return fs.mkdtempSync(path.join(baseDir, "python-env-"));
}

function withEnv(key, value, callback) {
  const previous = process.env[key];
  if (value === undefined) {
    delete process.env[key];
  } else {
    process.env[key] = value;
  }

  try {
    return callback();
  } finally {
    if (previous === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = previous;
    }
  }
}

test("findBundledFfmpegBin returns the bundled ffmpeg bin directory", () => {
  const tempDir = makeTempDir();
  const runtimeRoot = path.join(tempDir, "runtime");
  const ffmpegBinDir = path.join(runtimeRoot, "tools", "ffmpeg", "bundle", "bin");

  fs.mkdirSync(ffmpegBinDir, { recursive: true });
  fs.writeFileSync(path.join(ffmpegBinDir, "ffmpeg.exe"), "", "utf8");

  assert.equal(findBundledFfmpegBin(runtimeRoot), ffmpegBinDir);
});

test("buildBackendEnv injects packaged runtime directories and prepends bundled ffmpeg to PATH", () => {
  const tempDir = makeTempDir();
  const bundleRoot = path.join(tempDir, "resources", "runtime", "backend");
  const dataRoot = path.join(tempDir, "user-data");
  const runtimeRoot = path.join(dataRoot, "runtime");
  const ffmpegBinDir = path.join(runtimeRoot, "tools", "ffmpeg", "bundle", "bin");

  fs.mkdirSync(bundleRoot, { recursive: true });
  fs.mkdirSync(ffmpegBinDir, { recursive: true });
  fs.writeFileSync(path.join(ffmpegBinDir, "ffmpeg.exe"), "", "utf8");

  withEnv("PATH", "C:\\Windows\\System32", () => {
    const env = buildBackendEnv({ bundleRoot, dataRoot, runtimeRoot });
    const pathKey = Object.keys(env).find((key) => key.toUpperCase() === "PATH");

    assert.equal(env.PYTHONUTF8, "1");
    assert.equal(env.PYTHONIOENCODING, "utf-8");
    assert.equal(env.APP_BUNDLE_ROOT, bundleRoot);
    assert.equal(env.APP_DATA_ROOT, dataRoot);
    assert.equal(env.APP_RUNTIME_ROOT, runtimeRoot);
    assert.equal(env.HF_HOME, path.join(runtimeRoot, "cache", "huggingface"));
    assert.equal(env.XDG_CACHE_HOME, path.join(runtimeRoot, "cache"));
    assert.equal(env.TEMP, path.join(runtimeRoot, "temp"));
    assert.equal(env.TMP, path.join(runtimeRoot, "temp"));
    assert.ok(pathKey, "PATH key should exist");
    assert.equal(env[pathKey].split(path.delimiter)[0], ffmpegBinDir);
  });
});
