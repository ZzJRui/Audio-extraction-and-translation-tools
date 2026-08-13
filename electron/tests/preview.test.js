const test = require("node:test");
const assert = require("node:assert/strict");

const { buildPreviewModel } = require("../src/shared/preview");

const bilingualPreview = `1
00:00:00,000 --> 00:00:01,200
你好
Hello

2
00:00:01,500 --> 00:00:03,000
欢迎来到课程
Welcome to the lesson`;

const multilineBilingualPreview = `1
00:00:05,000 --> 00:00:08,000
第一行译文
第二行译文
First source line

2
00:00:08,500 --> 00:00:11,000
短译文
Original line one
Original line two`;

test("buildPreviewModel splits bilingual SRT into paired entries", () => {
  const result = buildPreviewModel({
    previewText: bilingualPreview,
    subtitleMode: "bilingual",
    searchQuery: "",
  });

  assert.equal(result.totalEntries, 2);
  assert.equal(result.entries[0].primaryText, "你好");
  assert.equal(result.entries[0].secondaryText, "Hello");
  assert.equal(result.entries[1].timeRange, "00:00:01,500 --> 00:00:03,000");
});

test("buildPreviewModel keeps multi-line bilingual groups intact", () => {
  const result = buildPreviewModel({
    previewText: multilineBilingualPreview,
    subtitleMode: "bilingual",
    searchQuery: "",
  });

  assert.equal(result.totalEntries, 2);
  assert.equal(result.entries[0].primaryText, "第一行译文\n第二行译文");
  assert.equal(result.entries[0].secondaryText, "First source line");
  assert.equal(result.entries[1].primaryText, "短译文");
  assert.equal(result.entries[1].secondaryText, "Original line one\nOriginal line two");
});

test("buildPreviewModel filters entries by search query", () => {
  const result = buildPreviewModel({
    previewText: bilingualPreview,
    subtitleMode: "bilingual",
    searchQuery: "lesson",
  });

  assert.equal(result.entries.length, 1);
  assert.equal(result.entries[0].secondaryText, "Welcome to the lesson");
});