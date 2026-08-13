(function initProgress(root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
    return;
  }
  root.TaskProgress = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function createProgressModule() {
  const STAGES = [
    { key: "idle", label: "待开始" },
    { key: "validating", label: "自检中" },
    { key: "running_transcribe", label: "识别中" },
    { key: "running_translate", label: "翻译中" },
    { key: "running_export", label: "导出中" },
    { key: "success", label: "已完成" },
    { key: "failure", label: "失败" },
  ];

  function inferStatusFromMessage(message) {
    const text = String(message || "");
    if (!text) {
      return "idle";
    }
    if (text.includes("语音识别") || text.includes("识别完成")) {
      return "running_transcribe";
    }
    if (text.includes("翻译")) {
      return "running_translate";
    }
    if (text.includes("导出") || text.includes("已生成") || text.includes("输出到目录")) {
      return "running_export";
    }
    if (text.includes("准备环境") || text.includes("输出目录") || text.includes("首次运行") || text.includes("清理")) {
      return "validating";
    }
    return "validating";
  }

  function classifyLogLevel(message) {
    const text = String(message || "");
    if (!text) {
      return "info";
    }

    const lowerText = text.toLowerCase();
    if (text.includes("失败") || lowerText.includes("error") || lowerText.includes("traceback") || lowerText.includes("exception")) {
      return "error";
    }
    if (text.includes("首次运行") || text.includes("警告") || lowerText.includes("warning")) {
      return "warning";
    }
    return "info";
  }

  function getStageLabel(stageKey) {
    const match = STAGES.find((stage) => stage.key === stageKey);
    return match ? match.label : "待开始";
  }

  return {
    STAGES,
    classifyLogLevel,
    getStageLabel,
    inferStatusFromMessage,
  };
});