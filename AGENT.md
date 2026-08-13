# AGENT

## 项目定位

这是一个本地音频字幕提取与翻译工具。
当前主入口是 **Electron 三栏工作台**，同时保留 Python GUI 作为兼容回退入口。

核心链路保持不变：
1. 读取音频
2. Whisper 识别
3. 字幕标准化与拆分
4. 按场景翻译
5. 导出 `SRT`

## 当前架构约定

### 桌面端
- `electron/src/main/main.js` 负责窗口与系统能力
- `electron/src/main/preload.js` 负责受限 IPC 桥接
- `electron/src/renderer/` 负责 GUI、状态机、日志和预览
- 渲染层不得直接访问 Node 能力

### 运行时路径
- `bundle root` 是只读程序资源目录
- `data root` 是用户可写目录
- `runtime root` 是缓存、模型和临时文件目录
- 打包态必须优先使用内置 Python，不再把系统 Python 作为首选
- 打包态必须优先使用安装包内的 `ffmpeg`，不依赖系统 `PATH`

### Python 后端
- `backend_runner.py` 是 Electron / GUI 的统一后端入口
- `app_service.py` 负责任务编排
- `transcribe.py` 负责 Whisper 调用
- `translate.py` 负责翻译调用
- `subtitle.py` 负责字幕标准化与导出
- `stability.py` 负责运行环境准备、启动自检和诊断日志
- `config.py` 统一处理 bundle root / data root / runtime root 的路径选择

## Windows 打包约定

首版安装包采用 `electron-builder + NSIS`：
- `npm run build:runtime` 生成 `.runtime-build/`
- `npm run dist:win:dir` 生成 `dist/win-unpacked/`
- `npm run dist:win` 生成 NSIS `Setup.exe`

`.runtime-build/` 需要至少包含：
- `backend/`：Python 后端脚本与 `.env.example`
- `python/`：内置 Python 运行时
- `tools/ffmpeg/`：内置 ffmpeg

打包时 Python 后端脚本不得放进 `app.asar`，而是通过 `extraResources` 进入 `resources/runtime/`。

## 关键协作原则

- Electron 只负责桌面壳、交互和状态呈现
- Whisper、翻译、导出等业务能力继续留在 Python
- 首版只做单任务工作台，不引入历史任务、多任务队列或取消任务
- 若修改进度协议，优先保持对 `__PROGRESS__:` 兼容
- 安装版不得向安装目录写入 `.env`、输出文件、日志或缓存

## 启动自检规则

无论入口来自 Electron、PySide6、Tkinter 还是 CLI，任务开始前都必须保留统一的启动自检。
至少覆盖：
- Python 可执行路径
- GUI 后端标识
- `ffmpeg`
- 输出目录可写性
- `.env` 是否存在
- 翻译模式下的 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`

结果等级保持：
- `fatal`
- `warning`
- `info`

用户可见错误文案需要友好：
- 缺失 `ffmpeg` 或内置 Python 时，前台主文案应落在“应用环境异常，请重新安装应用”这一层
- 技术细节保留在日志和错误详情里

## 运行入口约定

推荐入口：
- `run_electron.bat`
- `npm run start`

兼容入口：
- `run_gui.bat`
- `python gui.py`
- `python main.py`

## 文档同步要求

如果修改以下内容，必须同步更新 `README.md` 和本文件：
- 主运行入口
- 桌面架构分层
- 路径契约
- Windows 打包命令
- 启动自检行为
- Python 后端职责边界

## 测试要求

涉及 Electron 桌面层时，至少补充或维护：
- `electron/tests/python-task.test.js`
- `electron/tests/state.test.js`
- `electron/tests/validation.test.js`
- `electron/tests/preview.test.js`
- `electron/tests/package.test.js`

提交前优先执行：

```bash
npm run test:electron
npm run check:electron
python -m unittest discover -s tests -v
```

如果因为环境缺依赖导致某项无法执行，需要在交付说明里明确写出原因。
