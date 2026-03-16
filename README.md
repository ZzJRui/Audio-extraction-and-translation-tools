# 音频字幕提取与翻译工具

一个命令行 Python 小工具，用于将录音自动转为字幕，并根据指定情景生成中文翻译字幕与双语字幕。

## 功能

- 使用 `faster-whisper` 识别音频内容
- 可按需生成原文、译文或双语其中一种字幕
- 使用 DeepSeek 或 OpenAI 兼容接口进行情景翻译
- 只输出当前选择的 `SRT` 文件，减少无用结果

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

```bash
python main.py
```

程序每次启动新任务前，会自动清空 `input/` 和 `output/` 目录中的历史文件。

因此建议：

- 不要把需要长期保存的音频放在 `input/`
- 当前任务的音频可以放在项目外任意位置，然后输入完整路径
- 如果你仍想使用 `input/`，请在程序启动后的提示阶段再准备本次音频

程序会继续让你选择字幕输出类型：

```text
1. 原文字幕
2. 译文字幕
3. 双语字幕
```

示例输入：

```text
音频路径: D:\Audio\audio.mp3
翻译情景: 排球比赛解说
字幕类型: 3
```

## 输出文件

程序每次只输出一个文件：

- 选择原文时：`output/original.srt`
- 选择译文时：`output/translation.srt`
- 选择双语时：`output/bilingual.srt`
