# 音频字幕提取与翻译工具

一个支持命令行和桌面 GUI 的本地字幕工具，用于将录音自动转为字幕，并根据指定情景生成中文翻译字幕与双语字幕。

## 功能

- 使用 `faster-whisper` 识别音频内容
- 可按需生成原文、译文或双语其中一种字幕
- 使用 DeepSeek 或 OpenAI 兼容接口进行情景翻译
- 只输出当前选择的 `SRT` 文件，减少无用结果
- 优先使用 `PySide6` 桌面界面；若当前环境的 Qt 运行库异常，会自动回退到内置 Tkinter 界面

## 项目结构

```text
project/
├─ input/
│  └─ audio.mp3
├─ output/
│  ├─ original.srt
│  ├─ translation.srt
│  ├─ bilingual.srt
├─ main.py
├─ transcribe.py
├─ translate.py
├─ subtitle.py
├─ config.py
├─ app_service.py
├─ gui.py
└─ requirements.txt
```

## 安装依赖

```bash
pip install -r requirements.txt
```

另外请确认本机已经安装 `ffmpeg` 并可在命令行直接使用。

## 配置 API

复制 `.env.example` 的内容到你的环境变量配置中，至少要设置：

```bash
LLM_API_KEY=你的Key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

如果你使用 OpenAI 兼容网关，也可以改成自己的 `LLM_BASE_URL` 和模型名。

## 运行

推荐方式：

双击 `run_gui.bat`

或者：

```bash
python gui.py
```

说明：

- 若本机 `PySide6` 环境正常，会启动增强版桌面界面
- 若 `PySide6` 因 Qt DLL 问题无法加载，会自动回退到内置 Tkinter 图形界面

备用方式：

```bash
python main.py
```

GUI 模式下每次开始任务前，只会自动清理 `output/` 目录中的历史字幕文件，不会删除你选择的原始音频。

CLI 模式下仍保留旧逻辑：启动后会清理 `input/` 和 `output/`。

## 输出文件

程序每次只输出一个文件：

- 选择原文时：`output/original.srt`
- 选择译文时：`output/translation.srt`
- 选择双语时：`output/bilingual.srt`

## 错误提示

程序默认使用简洁中文提示，不会直接打印 Python 报错堆栈。

例如：

- 找不到音频文件时，会提示检查路径
- API Key 无效时，会提示检查 `.env`
- 网络异常时，会提示稍后重试

## GUI 界面说明

桌面版采用单窗口布局：

- 左侧：音频选择、字幕类型、翻译情景、开始生成
- 右侧：运行日志、输出文件、字幕预览
- 底部：打开输出目录、重新开始、退出

如果选择原文字幕，翻译情景输入框会自动禁用。

## 打包为 EXE

推荐使用 `PyInstaller` 的 `onedir` 模式：

```bash
pip install pyinstaller
pyinstaller --noconsole --onedir --name AudioSubtitleTool --add-data "tools;tools" --add-data ".env.example;." gui.py
```

打包完成后，直接双击生成的 `AudioSubtitleTool.exe` 即可打开桌面软件。
