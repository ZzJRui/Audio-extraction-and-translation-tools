(function initRendererState(root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory(require("../shared/progress"));
    return;
  }
  root.RendererState = factory(root.TaskProgress);
})(typeof globalThis !== "undefined" ? globalThis : this, function createRendererState(taskProgress) {
  function createInitialState() {
    return {
      status: "idle",
      latestMessage: "等待开始",
      modelDownloadHint: false,
      result: null,
      errorMessage: "",
      progressLog: [],
      startedAt: null,
    };
  }

  function reduceState(state, event) {
    const currentState = state || createInitialState();
    switch (event.type) {
      case "task/start":
        return {
          ...currentState,
          status: "validating",
          latestMessage: "开始执行任务...",
          modelDownloadHint: false,
          result: null,
          errorMessage: "",
          progressLog: [],
          startedAt: Date.now(),
        };
      case "task/progress": {
        const nextStatus = taskProgress.inferStatusFromMessage(event.message);
        return {
          ...currentState,
          status: nextStatus,
          latestMessage: event.message,
          modelDownloadHint:
            currentState.modelDownloadHint || String(event.message || "").includes("首次运行可能需要下载 Whisper 模型"),
          progressLog: currentState.progressLog.concat(String(event.message || "")),
        };
      }
      case "task/success":
        return {
          ...currentState,
          status: "success",
          result: event.result,
          errorMessage: "",
          latestMessage: "任务完成。",
        };
      case "task/failure":
        return {
          ...currentState,
          status: "failure",
          errorMessage: event.errorMessage || "任务执行失败。",
          latestMessage: event.errorMessage || "任务执行失败。",
        };
      case "task/reset":
        return createInitialState();
      default:
        return currentState;
    }
  }

  return {
    createInitialState,
    reduceState,
  };
});
