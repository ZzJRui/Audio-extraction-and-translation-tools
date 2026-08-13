const path = require("node:path");
const { spawn } = require("node:child_process");

function buildLaunchEnv(sourceEnv = process.env) {
  const nextEnv = { ...sourceEnv };
  delete nextEnv.ELECTRON_RUN_AS_NODE;
  return nextEnv;
}

function getAppRoot() {
  return path.resolve(__dirname, "..", "..");
}

function startElectron(options = {}) {
  const electronBinary = require("electron");
  const appRoot = options.appRoot || getAppRoot();
  const env = options.env || buildLaunchEnv(process.env);

  return spawn(electronBinary, [appRoot], {
    stdio: options.stdio || "inherit",
    env,
    windowsHide: false,
  });
}

if (require.main === module) {
  const child = startElectron();

  child.on("error", (error) => {
    console.error(error && error.message ? error.message : String(error));
    process.exit(1);
  });

  child.on("exit", (code) => {
    process.exit(code == null ? 0 : code);
  });
}

module.exports = {
  buildLaunchEnv,
  getAppRoot,
  startElectron,
};