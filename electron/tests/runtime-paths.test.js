const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const {
  getBundleRoot,
  getDataRoot,
  getEnvFilePath,
  getEnvTemplatePath,
  getReadonlyRuntimeRoot,
  getWritableRuntimeRoot,
  resolveDevelopmentRuntimeRoot,
} = require("../src/main/runtime-paths");

test("resolveDevelopmentRuntimeRoot prefers sibling runtime over explicit and dot runtime", () => {
  const projectRoot = path.join("D:\\", "workspace", "demo-app");
  const siblingRuntime = path.join("D:\\", "workspace", "demo-app_runtime");
  const explicitRuntime = path.join(projectRoot, ".custom-runtime");
  const dotRuntime = path.join(projectRoot, ".runtime");

  const result = resolveDevelopmentRuntimeRoot({
    projectRoot,
    explicitRuntimeRoot: explicitRuntime,
    existingPaths: [dotRuntime, explicitRuntime, siblingRuntime],
  });

  assert.equal(result, path.resolve(siblingRuntime));
});

test("packaged roots split bundle, data, and writable runtime", () => {
  const resourcesPath = path.join("C:\\", "Program Files", "Audio Subtitle Tool", "resources");
  const userDataPath = path.join("C:\\", "Users", "demo", "AppData", "Roaming", "audio-subtitle-tool");

  assert.equal(
    getBundleRoot({ isPackaged: true, resourcesPath }),
    path.join(resourcesPath, "runtime", "backend")
  );
  assert.equal(
    getReadonlyRuntimeRoot({ isPackaged: true, resourcesPath }),
    path.join(resourcesPath, "runtime")
  );
  assert.equal(getDataRoot({ isPackaged: true, userDataPath }), path.resolve(userDataPath));
  assert.equal(
    getWritableRuntimeRoot({ isPackaged: true, userDataPath }),
    path.join(path.resolve(userDataPath), "runtime")
  );
});

test("env paths point to writable data root and readonly template in packaged mode", () => {
  const resourcesPath = path.join("C:\\", "Program Files", "Audio Subtitle Tool", "resources");
  const userDataPath = path.join("C:\\", "Users", "demo", "AppData", "Roaming", "audio-subtitle-tool");

  assert.equal(
    getEnvFilePath({ isPackaged: true, userDataPath }),
    path.join(path.resolve(userDataPath), ".env")
  );
  assert.equal(
    getEnvTemplatePath({ isPackaged: true, resourcesPath }),
    path.join(resourcesPath, "runtime", "backend", ".env.example")
  );
});
