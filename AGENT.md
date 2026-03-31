# AGENT

## 项目定位

这是一个本地音频字幕提取与翻译工具，当前主入口是 GUI，同时保留 CLI。

核心链路：

1. 读取音频
2. Whisper 识别
3. 字幕标准化与拆分
4. 按场景翻译
5. 导出 `SRT`

## 当前稳定性约定

- 唯一推荐主运行时是 **Anaconda Python 3.13**
- `gui.py` 优先走 `PySide6`
- 当 Qt 运行时不可用时，自动回退到 **Tkinter**
- `Tkinter` 回退是正式保留能力，不是异常时的临时方案
- GUI 与 CLI 都必须经过统一的 **启动自检**

## 启动自检规则

启动自检至少覆盖以下内容：

- Python 可执行路径
- GUI 后端
- `ffmpeg`
- 输出目录可写性
- `.env` 是否存在
- 翻译模式下 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`

结果分级固定为：

- `fatal`
- `warning`
- `info`

任何涉及启动链路、环境发现、GUI 回退、诊断日志的修改，都要以这套规则为准。

## 代码组织共识

- `app_service.py` 负责任务编排
- `transcribe.py` 负责 Whisper 调用
- `translate.py` 负责翻译调用
- `subtitle.py` 负责字幕标准化与导出
- `stability.py` 负责运行时准备、启动自检、模型缓存提示、诊断日志
- `backend_runner.py` 是 GUI 后端入口
- `gui.py` 保持前端层职责，不把业务细节散落进去

## 文档同步要求

- 修改运行方式、环境要求、回退规则、自检行为时，必须同步更新 `README`
- 修改 README 中声明的稳定性约定时，必须同步更新本 `AGENT.md`
- README 和 AGENT 对同一件事不能给出互相冲突的说法

## 测试要求

- 涉及启动链路和环境检测的改动必须补测试
- 涉及 PySide6 / Tkinter 回退逻辑的改动必须补测试
- 涉及字幕拆分或格式化的改动优先补到 `tests/`
- 提交前默认跑：`python -m unittest discover -s tests -v`

## 排查优先级

遇到“不能用”类问题时，优先检查：

1. 启动自检是否有 `fatal`
2. `ffmpeg` 是否可用
3. 当前后端是 `PySide6` 还是 `Tkinter`
4. `.env` 是否完整
5. `output/logs/` 是否生成了诊断日志
