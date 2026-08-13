const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const packageJsonPath = path.join(__dirname, "..", "..", "package.json");
const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));

test("package scripts include runtime assembly and Windows distribution commands", () => {
  assert.equal(packageJson.scripts.start, "node electron/scripts/start.js");
  assert.equal(packageJson.scripts["build:runtime"], "node electron/scripts/build-runtime.js");
  assert.equal(packageJson.scripts["dist:win"], "npm run build:runtime && electron-builder --win nsis");
  assert.equal(packageJson.scripts["dist:win:dir"], "npm run build:runtime && electron-builder --win dir");
});

test("package uses electron-builder with NSIS and runtime extraResources", () => {
  assert.ok(packageJson.devDependencies["electron-builder"]);
  assert.equal(packageJson.build.productName, "音频字幕提取与翻译工具");
  assert.equal(packageJson.build.directories.output, "dist");
  assert.deepEqual(packageJson.build.win.target, ["nsis"]);
  assert.equal(packageJson.build.nsis.oneClick, false);
  assert.equal(packageJson.build.nsis.allowToChangeInstallationDirectory, true);

  const runtimeResource = packageJson.build.extraResources.find((entry) => entry.to === "runtime");
  assert.ok(runtimeResource);
  assert.equal(runtimeResource.from, ".runtime-build");
});
