# 音频字幕提取与翻译工具

这是一个本地桌面工具，用来把音频转成 `SRT` 字幕，并按需输出原文、译文或双语字幕。

当前主界面已经切到 **Electron 三栏工作台**：
- 左栏负责任务配置
- 中栏负责状态和日志
- 右栏负责结果和字幕预览

Python 后端仍然是唯一任务执行引擎，Whisper 识别、翻译和导出链路继续复用现有实现。

## 推荐启动方式

首选 Electron 版桌面工作台：

```bat
run_electron.bat
```

如果你还没有安装 Electron 依赖，先执行：

```bash
npm install
```

兼容保留的旧入口：

```bat
run_gui.bat
```

旧版 Python GUI 仍可作为回退方案，但后续主线界面以 Electron 为准。

## Electron 架构

Electron 版采用 `main + preload + renderer` 结构：
- `electron/src/main/main.js` 负责窗口、文件选择、启动 Python、打开目录和文件
- `electron/src/main/preload.js` 负责向渲染层暴露受限 IPC API
- `electron/src/renderer/` 负责三栏 GUI、状态管理、日志和预览
- `electron/src/main/python-task.js` 负责 Python 任务适配层
- `electron/src/main/runtime-paths.js` 负责开发态与安装态的路径分层

当前首版支持：
- 选择音频文件
- 选择字幕模式：原文 / 译文 / 双语
- 在译文和双语模式下填写翻译场景
- 启动任务并实时查看阶段状态
- 查看运行日志
- 打开输出文件、打开输出目录、复制输出路径
- 搜索字幕预览

当前首版暂不支持：
- 任务取消
- 多任务队列
- 历史任务

## Python 后端复用说明

Electron 不重写业务链路，而是继续调用根目录的 Python 后端：
- `backend_runner.py` 作为 Electron 侧任务入口
- `app_service.py` 继续负责任务编排
- `backend_client.py` 中的 `__PROGRESS__:` 仍是进度前缀协议

渲染层提交给 Python 的字段：
- `audio_path`
- `subtitle_mode`
- `scene`
- `gui_backend = "electron"`

Python 回包至少包含：
- `output_file`
- `output_dir`
- `subtitle_mode`
- `segment_count`
- `used_translation`
- `preview_text`

## 路径分层

开发态和安装态现在共用一套路径契约：
- `bundle root`：只读程序资源目录
- `data root`：用户可写目录
- `runtime root`：缓存、临时文件和模型缓存目录

开发态默认行为：
- `.env` 仍然放在项目根目录
- 输出目录默认是项目根下的 `output/`
- `.runtime/` 或同级运行时目录可继续作为缓存和模型目录

安装态默认行为：
- Electron 安装目录只放程序本体和后端资源
- `.env`、`output/`、日志、缓存、模型统一写入 `app.getPath("userData")`
- `ffmpeg` 与内置 Python 都从安装包的 `resources/runtime/` 下定位

## Windows 安装包

首版 Windows 分发采用 `electron-builder + NSIS`：
- `dist/*.exe`：正式发布的安装包
- `dist/win-unpacked/`：本地烟测和排障用目录

打包前需要准备：
- Windows 构建机
- Node.js / npm
- Python 3.13
- 项目内可读取的 `ffmpeg` 目录，优先放在 `tools/ffmpeg/`

打包命令：

```bash
npm run build:runtime
npm run dist:win:dir
npm run dist:win
```

说明：
- `build:runtime` 会组装 `.runtime-build/`，包含后端脚本、内置 Python 和内置 ffmpeg
- `dist:win:dir` 用来生成 unpacked 目录，适合先做本地验证
- `dist:win` 生成 NSIS 安装包 `Setup.exe`

## 环境要求

开发态推荐运行环境：
- Windows
- Python 3.13
- Node.js 18+

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

开发态项目会读取根目录下的 `.env`。翻译模式需要完整配置：

```bash
LLM_API_KEY=你的Key
LLM_BASE_URL=模型接口地址
LLM_MODEL=模型名称
```

说明：
- 原文字幕不依赖 LLM 配置
- 译文和双语模式必须提供完整的 LLM 配置
- 安装版会把模板 `.env.example` 初始化到用户数据目录下的 `.env`

## 启动自检

Python 后端在任务开始前仍会执行启动自检，重点检查：
- Python 可执行环境
- 当前 GUI 后端
- `ffmpeg` 是否可用
- 输出目录是否可写
- `.env` 是否存在
- 翻译模式下的 LLM 配置是否完整

如果是首次运行且本地还没有对应的 Whisper 模型缓存，日志里会提示首次运行可能较慢。这属于正常现象，不是卡死。

## 校验命令

Electron 侧目前提供一组 Node 校验命令：

```bash
npm run test:electron
npm run check:electron
```

Python 侧测试仍在 `tests/` 下维护，按需执行：

```bash
python -m unittest discover -s tests -v
```

## 旧版 Python GUI

旧版 GUI 仍然保留：
- `gui.py` 优先尝试 `PySide6`
- 如果 Qt 环境不可用，会自动回退到 `Tkinter`

这条回退链继续保留，主要用于兼容环境或紧急排障，不再作为主线界面演进方向。
