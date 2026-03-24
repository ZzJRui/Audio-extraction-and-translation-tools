# AGENT

## 项目概述

这是一个本地音频字幕提取与翻译工具，目标是把音频内容识别为字幕，并按需要输出：

- 原文字幕
- 中文字幕
- 双语字幕

项目当前以桌面 GUI 为主要使用方式，同时保留命令行入口。字幕生成流程大致为：

1. 读取音频文件
2. 使用 Whisper 进行语音识别
3. 对识别片段做字幕级标准化和拆分
4. 按场景调用 LLM 生成中文翻译
5. 输出 `SRT` 文件

## 技术栈

- Python 3
- `faster-whisper`
- `openai` Python SDK
- `srt`
- `PySide6`
- Windows `.bat` 启动脚本

## 常用开发命令

安装依赖：

```bash
pip install -r requirements.txt
```

启动桌面版：

```bash
python gui.py
```

或直接双击：

```bat
run_gui.bat
```

启动命令行版：

```bash
python main.py
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

打包桌面版：

```bash
pyinstaller --noconsole --onedir --name AudioSubtitleTool --add-data "tools;tools" --add-data ".env.example;." gui.py
```

## 环境与配置

项目通过 `.env` 读取配置，示例见 `.env.example`。

核心配置项：

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `WHISPER_MODEL_SIZE`
- `WHISPER_DEVICE`
- `WHISPER_COMPUTE_TYPE`
- `SOURCE_LANGUAGE`
- `TRANSLATION_BATCH_SIZE`
- `OUTPUT_DIR`

运行前需要确保：

- 本机可用 `ffmpeg`
- 翻译功能所需的 LLM 配置完整
- GUI 环境可用 `PySide6`

## 目录结构

```text
.
├─ app_service.py        # 任务编排，串联识别、字幕标准化、翻译、导出
├─ backend_runner.py     # GUI 子进程入口，负责桥接前端与服务层
├─ config.py             # 配置加载与运行目录解析
├─ gui.py                # PySide6 桌面界面
├─ main.py               # 命令行入口
├─ subtitle.py           # 字幕排版、换行、长句拆分、SRT 生成
├─ transcribe.py         # Whisper 识别封装
├─ translate.py          # LLM 翻译提示词与翻译调用
├─ run.bat               # 命令行启动脚本
├─ run_gui.bat           # GUI 启动脚本
├─ requirements.txt      # Python 依赖
├─ README.md             # 项目说明
├─ 使用说明.md            # 中文使用说明
├─ tests/
│  └─ test_subtitle_pipeline.py
└─ .env.example
```

## 当前架构共识

- GUI 是当前主入口。
- `app_service.py` 是业务主链路，尽量把流程性逻辑放在这里。
- 识别、翻译、字幕排版分别放在独立模块中，避免把实现细节堆进 GUI。
- 字幕优化应优先在导出前的标准化阶段处理，而不是散落在界面层。
- 翻译输出必须与字幕片段一一对应。

## 开发约定

- 优先保持 GUI、CLI 两条入口都可运行，除非明确决定废弃其中之一。
- 涉及字幕行为变更时，优先补测试到 `tests/test_subtitle_pipeline.py`。
- 修改翻译策略时，保持 JSON 输出格式不变，避免影响 GUI 与后端桥接。
- 不要把临时调试逻辑留在正式运行路径里。
- 配置读取统一走 `config.py`，避免在各处直接读环境变量。

## 适合后续继续补充的内容

- 示例输入输出
- 发布打包流程
- 常见故障排查
- 模型选择建议
