const test = require("node:test");
const assert = require("node:assert/strict");

const { inferStatusFromMessage } = require("../src/shared/progress");

test("inferStatusFromMessage keeps generated-output messages in export stage", () => {
  assert.equal(inferStatusFromMessage("已生成 bilingual.srt"), "running_export");
  assert.equal(inferStatusFromMessage("已输出到目录: D:/demo/output"), "running_export");
});