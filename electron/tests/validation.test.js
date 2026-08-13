const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { validateTaskInput } = require("../src/shared/validation");

function makeAudioFile() {
  const baseDir = path.join(process.cwd(), ".tmp_test");
  fs.mkdirSync(baseDir, { recursive: true });
  const tempDir = fs.mkdtempSync(path.join(baseDir, "electron-validation-"));
  const filePath = path.join(tempDir, "sample.mp3");
  fs.writeFileSync(filePath, "demo", "utf8");
  return filePath;
}

test("validateTaskInput requires an audio file", () => {
  const result = validateTaskInput({
    audioPath: "",
    subtitleMode: "original",
    scene: "",
  });

  assert.equal(result.ok, false);
  assert.equal(result.fieldErrors.audioPath, "请选择音频文件。");
});

test("validateTaskInput rejects missing file paths", () => {
  const result = validateTaskInput({
    audioPath: "D:/missing/sample.mp3",
    subtitleMode: "original",
    scene: "",
  });

  assert.equal(result.ok, false);
  assert.equal(result.fieldErrors.audioPath, "找不到所选音频文件。");
});

test("validateTaskInput requires scene for translation modes", () => {
  const result = validateTaskInput({
    audioPath: makeAudioFile(),
    subtitleMode: "translation",
    scene: "   ",
  });

  assert.equal(result.ok, false);
  assert.equal(result.fieldErrors.scene, "请选择或填写翻译场景。");
});

test("validateTaskInput accepts original subtitles without scene", () => {
  const result = validateTaskInput({
    audioPath: makeAudioFile(),
    subtitleMode: "original",
    scene: "",
  });

  assert.equal(result.ok, true);
  assert.deepEqual(result.fieldErrors, {});
});
