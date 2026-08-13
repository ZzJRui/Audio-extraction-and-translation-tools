const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("appApi", {
  getAppContext() {
    return ipcRenderer.invoke("app:get-context");
  },
  getSettings() {
    return ipcRenderer.invoke("settings:get");
  },
  saveSettings(payload) {
    return ipcRenderer.invoke("settings:save", payload);
  },
  selectAudioFile() {
    return ipcRenderer.invoke("dialog:select-audio-file");
  },
  async runSubtitleTask(payload) {
    const response = await ipcRenderer.invoke("task:run", payload);
    if (!response.ok) {
      throw response.error;
    }
    return response.data;
  },
  onTaskProgress(listener) {
    const wrapped = (_event, payload) => listener(payload);
    ipcRenderer.on("task:progress", wrapped);
    return () => ipcRenderer.removeListener("task:progress", wrapped);
  },
  openOutputDirectory(targetPath) {
    return ipcRenderer.invoke("shell:open-output-directory", targetPath);
  },
  openFile(targetPath) {
    return ipcRenderer.invoke("shell:open-file", targetPath);
  },
  copyText(text) {
    return ipcRenderer.invoke("clipboard:copy", text);
  },
});