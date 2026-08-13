const test = require("node:test");
const assert = require("node:assert/strict");

const { createInitialState, reduceState } = require("../src/renderer/state");

test("reduceState moves into transcribe stage from progress text", () => {
  const nextState = reduceState(createInitialState(), {
    type: "task/progress",
    message: "2/4 正在进行语音识别...",
  });

  assert.equal(nextState.status, "running_transcribe");
  assert.equal(nextState.latestMessage, "2/4 正在进行语音识别...");
});

test("reduceState marks model download hint when progress warns about first run", () => {
  const nextState = reduceState(createInitialState(), {
    type: "task/progress",
    message: "首次运行可能需要下载 Whisper 模型，耗时会明显变长。",
  });

  assert.equal(nextState.status, "validating");
  assert.equal(nextState.modelDownloadHint, true);
});

test("reduceState captures success result", () => {
  const nextState = reduceState(createInitialState(), {
    type: "task/success",
    result: {
      output_file: "D:/demo/output/bilingual.srt",
      output_dir: "D:/demo/output",
      subtitle_mode: "bilingual",
      preview_text: "demo",
    },
  });

  assert.equal(nextState.status, "success");
  assert.equal(nextState.result.output_file, "D:/demo/output/bilingual.srt");
});
