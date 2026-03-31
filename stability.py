import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from config import AppConfig, get_app_root, get_runtime_root

TRANSLATION_MODES = {"translation", "bilingual"}


@dataclass(frozen=True)
class StartupCheckItem:
    level: str
    code: str
    message: str


@dataclass(frozen=True)
class StartupReport:
    python_executable: str
    gui_backend: str
    items: tuple[StartupCheckItem, ...]

    @property
    def has_fatal(self) -> bool:
        return any(item.level == "fatal" for item in self.items)


def prepare_runtime_environment(project_root: Path | None = None) -> None:
    root = project_root or get_app_root()
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    search_roots = [
        get_runtime_root() / "tools" / "ffmpeg",
        root / "tools" / "ffmpeg",
    ]
    for ffmpeg_root in search_roots:
        if not ffmpeg_root.exists():
            continue
        for ffmpeg_exe in ffmpeg_root.rglob("ffmpeg.exe"):
            bin_dir = str(ffmpeg_exe.parent)
            path_entries = os.environ.get("PATH", "").split(os.pathsep)
            if bin_dir not in path_entries:
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
            return


def _check_output_dir(output_dir: Path) -> StartupCheckItem:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = output_dir / ".startup-write-check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return StartupCheckItem("info", "output_dir_ready", f"输出目录可用: {output_dir.resolve()}")
    except Exception as exc:
        return StartupCheckItem("fatal", "output_dir_unavailable", f"输出目录不可写: {output_dir} ({exc})")


def collect_startup_report(
    config: AppConfig,
    gui_backend: str,
    subtitle_mode: str | None = None,
) -> StartupReport:
    items: list[StartupCheckItem] = [
        StartupCheckItem("info", "python_executable", f"Python 可执行文件: {sys.executable}"),
        StartupCheckItem("info", "gui_backend", f"当前界面后端: {gui_backend}"),
    ]

    if gui_backend == "tkinter":
        items.append(
            StartupCheckItem(
                "warning",
                "tkinter_fallback",
                "当前使用 Tkinter 回退界面；PySide6 仍保留为首选后端。",
            )
        )

    env_path = get_app_root() / ".env"
    if env_path.exists():
        items.append(StartupCheckItem("info", "dotenv_found", f"检测到配置文件: {env_path.name}"))
    else:
        items.append(
            StartupCheckItem(
                "warning",
                "dotenv_missing",
                "未找到 .env，原文字幕可以继续运行，翻译模式会被阻止。",
            )
        )

    if shutil.which("ffmpeg") is None:
        items.append(
            StartupCheckItem("fatal", "ffmpeg_missing", "未检测到 ffmpeg，请先安装或把它加入 PATH。")
        )
    else:
        items.append(StartupCheckItem("info", "ffmpeg_ready", "已检测到 ffmpeg。"))

    items.append(_check_output_dir(config.output_dir))

    if subtitle_mode in TRANSLATION_MODES:
        if not config.llm_api_key.strip():
            items.append(
                StartupCheckItem("fatal", "llm_api_key_missing", "翻译模式缺少 LLM_API_KEY。")
            )
        if not config.llm_base_url.strip():
            items.append(
                StartupCheckItem("fatal", "llm_base_url_missing", "翻译模式缺少 LLM_BASE_URL。")
            )
        if not config.llm_model.strip():
            items.append(
                StartupCheckItem("fatal", "llm_model_missing", "翻译模式缺少 LLM_MODEL。")
            )

    return StartupReport(
        python_executable=sys.executable,
        gui_backend=gui_backend,
        items=tuple(items),
    )


def format_startup_report(
    report: StartupReport,
    *,
    levels: Iterable[str] | None = None,
) -> list[str]:
    allowed = set(levels) if levels is not None else {"fatal", "warning", "info"}
    prefix_map = {"fatal": "[fatal]", "warning": "[warning]", "info": "[info]"}
    return [
        f"{prefix_map.get(item.level, '[info]')} {item.message}"
        for item in report.items
        if item.level in allowed
    ]


def _huggingface_cache_root() -> Path:
    hf_home = os.environ.get("HF_HOME", "").strip()
    if hf_home:
        return Path(hf_home)
    return Path.home() / ".cache" / "huggingface"


def should_warn_about_model_download(config: AppConfig) -> bool:
    model_value = config.whisper_model_size.strip()
    if not model_value:
        return False

    if any(sep in model_value for sep in ("/", "\\")):
        return False

    if Path(model_value).exists():
        return False

    snapshot_root = (
        _huggingface_cache_root()
        / "hub"
        / f"models--Systran--faster-whisper-{model_value}"
        / "snapshots"
    )
    if not snapshot_root.exists():
        return True

    return not any(path.is_dir() for path in snapshot_root.iterdir())


def write_task_diagnostic_log(
    *,
    output_dir: Path,
    python_executable: str,
    gui_backend: str,
    audio_path: str,
    subtitle_mode: str,
    startup_report: StartupReport,
    success: bool,
    error_summary: str | None,
    config: AppConfig,
) -> Path:
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir / f"task-{timestamp}.json"
    payload = {
        "timestamp_utc": timestamp,
        "python_executable": python_executable,
        "gui_backend": gui_backend,
        "audio_path": audio_path,
        "subtitle_mode": subtitle_mode,
        "startup_report": {
            "has_fatal": startup_report.has_fatal,
            "items": [asdict(item) for item in startup_report.items],
        },
        "success": success,
        "error_summary": error_summary,
        "config": {
            "whisper_model_size": config.whisper_model_size,
            "whisper_device": config.whisper_device,
            "whisper_compute_type": config.whisper_compute_type,
            "source_language": config.source_language,
            "llm_api_key_configured": bool(config.llm_api_key.strip()),
            "llm_base_url_configured": bool(config.llm_base_url.strip()),
            "llm_model_configured": bool(config.llm_model.strip()),
            "output_dir": str(output_dir.resolve()),
        },
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return log_path
