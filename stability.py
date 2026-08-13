import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from config import (
    AppConfig,
    get_app_root,
    get_bundle_root,
    get_env_file_path,
    get_runtime_root,
)

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


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path_obj in paths:
        normalized = str(path_obj.resolve(strict=False)).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(path_obj)
    return result


def _ffmpeg_root_candidates(project_root: Path) -> list[Path]:
    sibling_runtime_root = project_root.parent / f"{project_root.name}_runtime"
    dot_runtime_root = project_root / ".runtime"
    configured_runtime_root = get_runtime_root()
    bundle_root = get_bundle_root()
    readonly_runtime_root = bundle_root.parent if bundle_root.name == "backend" else bundle_root

    return _unique_paths(
        [
            configured_runtime_root / "tools" / "ffmpeg",
            readonly_runtime_root / "tools" / "ffmpeg",
            project_root / "tools" / "ffmpeg",
            dot_runtime_root / "tools" / "ffmpeg",
            sibling_runtime_root / "tools" / "ffmpeg",
        ]
    )


def _find_ffmpeg_executable(project_root: Path) -> Path | None:
    for ffmpeg_root in _ffmpeg_root_candidates(project_root):
        if not ffmpeg_root.exists():
            continue
        for ffmpeg_exe in ffmpeg_root.rglob("ffmpeg.exe"):
            return ffmpeg_exe
        for ffmpeg_binary in ffmpeg_root.rglob("ffmpeg"):
            return ffmpeg_binary
    return None


def _prepend_path(bin_dir: str) -> None:
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    normalized_entries = {entry.lower() for entry in path_entries if entry}
    if bin_dir.lower() not in normalized_entries:
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


def prepare_runtime_environment(project_root: Path | None = None) -> None:
    root = project_root or get_app_root()
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    ffmpeg_exe = _find_ffmpeg_executable(root)
    if ffmpeg_exe is None:
        return

    bin_dir = str(ffmpeg_exe.parent)
    _prepend_path(bin_dir)
    os.environ.setdefault("FFMPEG_BINARY", str(ffmpeg_exe))
    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", str(ffmpeg_exe))


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
        StartupCheckItem("info", "whisper_model_selected", f"当前 Whisper 模型: {config.normalized_whisper_model_size}"),
        StartupCheckItem(
            "info",
            "whisper_runtime",
            f"Whisper 运行参数: device={config.whisper_device}, compute_type={config.whisper_compute_type}, beam_size={config.whisper_beam_size}",
        ),
        StartupCheckItem(
            "info",
            "word_timestamps_enabled",
            f"词级时间对齐: {'开启' if config.whisper_word_timestamps else '关闭'}",
        ),
    ]

    if gui_backend == "tkinter":
        items.append(
            StartupCheckItem(
                "warning",
                "tkinter_fallback",
                "当前使用 Tkinter 回退界面；PySide6 仍保留为首选后端。",
            )
        )

    env_path = get_env_file_path()
    if env_path.exists():
        items.append(StartupCheckItem("info", "dotenv_found", f"检测到配置文件: {env_path}"))
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
            StartupCheckItem(
                "fatal",
                "ffmpeg_missing",
                "未检测到 ffmpeg 运行时，应用环境可能不完整。",
            )
        )
    else:
        items.append(StartupCheckItem("info", "ffmpeg_ready", "已检测到 ffmpeg。"))

    items.append(_check_output_dir(config.output_dir))

    model_size = config.normalized_whisper_model_size.strip().lower()
    if model_size == "tiny":
        items.append(
            StartupCheckItem(
                "warning",
                "whisper_tiny_quality",
                "当前 Whisper 模型为 tiny，识别速度更快，但识别稳定性和术语准确率会明显下降。",
            )
        )

    raw_source_language = (config.source_language or "").strip()
    if raw_source_language:
        items.append(
            StartupCheckItem(
                "info",
                "source_language_locked",
                f"已锁定源语言: {config.effective_source_language}",
            )
        )
    else:
        items.append(
            StartupCheckItem(
                "info",
                "source_language_defaulted",
                f"未显式设置源语言，当前默认按英文 ({config.effective_source_language}) 处理。",
            )
        )

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
    model_value = config.normalized_whisper_model_size.strip()
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
            "whisper_model_size": config.normalized_whisper_model_size,
            "whisper_device": config.whisper_device,
            "whisper_compute_type": config.whisper_compute_type,
            "source_language": config.source_language,
            "effective_source_language": config.effective_source_language,
            "whisper_beam_size": config.whisper_beam_size,
            "whisper_word_timestamps": config.whisper_word_timestamps,
            "llm_api_key_configured": bool(config.llm_api_key.strip()),
            "llm_base_url_configured": bool(config.llm_base_url.strip()),
            "llm_model_configured": bool(config.llm_model.strip()),
            "output_dir": str(output_dir.resolve()),
        },
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return log_path
