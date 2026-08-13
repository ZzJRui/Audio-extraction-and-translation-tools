(function initValidation(root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory(require("node:fs"));
    return;
  }
  root.TaskValidation = factory({
    existsSync() {
      return true;
    },
  });
})(typeof globalThis !== "undefined" ? globalThis : this, function createValidation(fs) {
  const TRANSLATION_MODES = new Set(["translation", "bilingual"]);

  function validateTaskInput({ audioPath, subtitleMode, scene }) {
    const fieldErrors = {};
    const normalizedAudioPath = String(audioPath || "").trim();
    const normalizedScene = String(scene || "").trim();

    if (!normalizedAudioPath) {
      fieldErrors.audioPath = "请选择音频文件。";
    } else if (fs && typeof fs.existsSync === "function" && !fs.existsSync(normalizedAudioPath)) {
      fieldErrors.audioPath = "找不到所选音频文件。";
    }

    if (TRANSLATION_MODES.has(subtitleMode) && !normalizedScene) {
      fieldErrors.scene = "请选择或填写翻译场景。";
    }

    return {
      ok: Object.keys(fieldErrors).length === 0,
      fieldErrors,
    };
  }

  return {
    TRANSLATION_MODES,
    validateTaskInput,
  };
});
