const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { runBackendTask, BackendTaskError, PROGRESS_PREFIX } = require("../src/main/python-task");

function makeTempDir() {
  const baseDir = path.join(process.cwd(), ".tmp_test");
  fs.mkdirSync(baseDir, { recursive: true });
  return fs.mkdtempSync(path.join(baseDir, "electron-node-"));
}

test("runBackendTask streams progress and returns parsed JSON", async () => {
  const tempDir = makeTempDir();
  const scriptPath = path.join(tempDir, "success.js");
  fs.writeFileSync(
    scriptPath,
    [
      "process.stdin.resume();",
      "process.stdin.on('end', () => {",
      `  process.stderr.write(${JSON.stringify(`${PROGRESS_PREFIX}2/4 正在进行语音识别...\n`)});`,
      "  process.stdout.write(JSON.stringify({ output_file: 'C:/demo/original.srt', subtitle_mode: 'original', preview_text: 'demo' }));",
      "});",
    ].join("\n"),
    "utf8"
  );

  const progressMessages = [];
  const result = await runBackendTask({
    command: process.execPath,
    args: [scriptPath],
    cwd: process.cwd(),
    payload: { subtitle_mode: "original" },
    onProgress: (message) => progressMessages.push(message),
  });

  assert.deepEqual(progressMessages, ["2/4 正在进行语音识别..."]);
  assert.equal(result.output_file, "C:/demo/original.srt");
  assert.equal(result.subtitle_mode, "original");
});

test("runBackendTask surfaces stderr when backend exits with failure", async () => {
  const tempDir = makeTempDir();
  const scriptPath = path.join(tempDir, "failure.js");
  fs.writeFileSync(
    scriptPath,
    [
      "process.stdin.resume();",
      "process.stdin.on('end', () => {",
      "  process.stderr.write('RuntimeError: 找不到 ffmpeg\\n');",
      "  process.exit(1);",
      "});",
    ].join("\n"),
    "utf8"
  );

  await assert.rejects(
    () =>
      runBackendTask({
        command: process.execPath,
        args: [scriptPath],
        cwd: process.cwd(),
        payload: { subtitle_mode: "original" },
      }),
    (error) => {
      assert.ok(error instanceof BackendTaskError);
      assert.match(error.message, /找不到 ffmpeg/);
      assert.equal(error.stderrText, "RuntimeError: 找不到 ffmpeg");
      return true;
    }
  );
});
