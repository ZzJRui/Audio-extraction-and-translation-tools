import os
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from config import AppConfig
from stability import prepare_runtime_environment, should_warn_about_model_download
from subtitle import (
    build_bilingual_subtitles,
    build_original_subtitles,
    build_translation_subtitles,
    normalize_segments,
    write_srt_file,
)
from transcribe import transcribe_audio
from translate import translate_segments

SCENE_PRESETS = [
    "日常对话",
    "排球比赛解说",
    "体育赛事",
    "动漫字幕",
    "医学讲解",
]

SUBTITLE_MODE_LABELS = {
    "original": "原文字幕",
    "translation": "译文字幕",
    "bilingual": "双语字幕",
}

TRANSLATION_MODES = {"translation", "bilingual"}
ProgressCallback = Callable[[str], None]


class _WorkspaceTemporaryDirectory:
    def __init__(self, suffix: str | None = None, prefix: str | None = None, dir: str | os.PathLike[str] | None = None):
        base_dir = Path(dir) if dir is not None else (Path.cwd() / ".tmp_test")
        base_dir.mkdir(parents=True, exist_ok=True)
        name_prefix = prefix or "tmp"
        name_suffix = suffix or ""
        self.name = str(base_dir / f"{name_prefix}{uuid.uuid4().hex}{name_suffix}")
        Path(self.name).mkdir(parents=True, exist_ok=False)

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type, exc, tb) -> None:
        shutil.rmtree(self.name, ignore_errors=True)


if "unittest" in sys.modules:
    tempfile.TemporaryDirectory = _WorkspaceTemporaryDirectory


@dataclass(frozen=True)
class TaskResult:
    subtitle_mode: str
    output_file: Path
    output_dir: Path
    segment_count: int
    used_translation: bool
    preview_text: str


def _emit_progress(progress_callback: ProgressCallback | None, message: str) -> None:
    if progress_callback:
        progress_callback(message)


def sanitize_audio_path(audio_path: str | Path) -> Path:
    cleaned = str(audio_path).strip().strip('"').strip("'")
    return Path(cleaned)


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def clear_directory_files(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

    for child in path.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        except Exception as exc:
            raise RuntimeError(f"清理失败: {child} -> {exc}") from exc


def prepare_task_dirs(
    project_root: Path,
    output_dir: Path,
    *,
    clear_input: bool,
    clear_output: bool,
    progress_callback: ProgressCallback | None = None,
) -> None:
    if not clear_input and not clear_output:
        return

    input_dir = project_root / "input"
    if clear_input and clear_output:
        _emit_progress(progress_callback, "正在清理上一轮任务留下的输入和输出文件...")
    elif clear_output:
        _emit_progress(progress_callback, "正在清理上一轮任务留下的输出文件...")
    else:
        _emit_progress(progress_callback, "正在清理上一轮任务留下的输入文件...")

    if clear_input:
        clear_directory_files(input_dir)
    if clear_output:
        clear_directory_files(output_dir)

    _emit_progress(progress_callback, "清理完成。")


def validate_runtime(config: AppConfig) -> None:
    del config
    if shutil.which("ffmpeg") is None:
        raise EnvironmentError("未检测到 ffmpeg，请先安装并加入系统 PATH。")


def initialize_runtime(project_root: Path, config: AppConfig) -> None:
    prepare_runtime_environment(project_root)
    validate_runtime(config)


def validate_task_request(
    audio_path: str | Path,
    subtitle_mode: str,
    scene: str | None,
    config: AppConfig,
) -> tuple[Path, str]:
    normalized_path = sanitize_audio_path(audio_path)
    if not str(normalized_path):
        raise ValueError("音频路径不能为空。")
    if subtitle_mode not in SUBTITLE_MODE_LABELS:
        raise ValueError("字幕类型无效。")
    if not normalized_path.exists():
        raise FileNotFoundError(str(normalized_path))

    normalized_scene = (scene or "").strip()
    if subtitle_mode in TRANSLATION_MODES:
        if not normalized_scene:
            raise ValueError("翻译情景不能为空。")
        if not config.llm_api_key:
            raise ValueError("未配置 LLM_API_KEY，无法生成译文或双语字幕。")
        if not config.llm_base_url:
            raise ValueError("未配置 LLM_BASE_URL，请先在 .env 中填写模型接口地址。")
        if not config.llm_model:
            raise ValueError("未配置 LLM_MODEL，请先在 .env 中填写模型名称。")
    else:
        normalized_scene = ""

    return normalized_path, normalized_scene


def execute_subtitle_task(
    project_root: Path,
    config: AppConfig,
    audio_path: str | Path,
    subtitle_mode: str,
    scene: str | None = None,
    *,
    progress_callback: ProgressCallback | None = None,
) -> TaskResult:
    initialize_runtime(project_root, config)

    output_dir = config.output_dir
    _emit_progress(progress_callback, "1/4 正在准备环境和输出目录...")
    ensure_output_dir(output_dir)
    clear_directory_files(output_dir)
    normalized_path, normalized_scene = validate_task_request(
        audio_path,
        subtitle_mode,
        scene,
        config,
    )
    _emit_progress(progress_callback, "环境与目录准备完成。")

    if should_warn_about_model_download(config):
        _emit_progress(progress_callback, "首次运行可能需要下载 Whisper 模型，耗时会明显变长。")

    _emit_progress(progress_callback, "2/4 正在进行语音识别...")
    recognized_segments = transcribe_audio(normalized_path, config)
    segments = normalize_segments(recognized_segments)
    _emit_progress(
        progress_callback,
        f"识别完成，共 {len(recognized_segments)} 条片段，优化后生成 {len(segments)} 条字幕。",
    )

    translations: list[str] | None = None
    if subtitle_mode in TRANSLATION_MODES:
        _emit_progress(progress_callback, "3/4 正在进行情景翻译...")
        translations = translate_segments(segments, normalized_scene, config)
        _emit_progress(progress_callback, "情景翻译完成。")
    else:
        _emit_progress(progress_callback, "3/4 已跳过翻译，当前仅输出原文字幕。")

    _emit_progress(progress_callback, "4/4 正在导出字幕文件...")
    if subtitle_mode == "original":
        output_file = output_dir / "original.srt"
        write_srt_file(output_file, build_original_subtitles(segments))
    elif subtitle_mode == "translation":
        output_file = output_dir / "translation.srt"
        write_srt_file(output_file, build_translation_subtitles(segments, translations or []))
    else:
        output_file = output_dir / "bilingual.srt"
        write_srt_file(output_file, build_bilingual_subtitles(segments, translations or []))

    _emit_progress(progress_callback, f"已生成 {output_file.name}")
    _emit_progress(progress_callback, f"已输出到目录: {output_dir.resolve()}")

    return TaskResult(
        subtitle_mode=subtitle_mode,
        output_file=output_file,
        output_dir=output_dir,
        segment_count=len(segments),
        used_translation=subtitle_mode in TRANSLATION_MODES,
        preview_text=output_file.read_text(encoding="utf-8"),
    )


def build_error_message(exc: Exception) -> tuple[str, str | None]:
    if isinstance(exc, FileNotFoundError):
        return (
            f"处理失败：找不到音频文件：{exc}",
            "建议：请检查路径是否正确，Windows 路径可直接粘贴，带引号也可以。",
        )
    if isinstance(exc, PermissionError):
        return (
            "处理失败：文件正在被占用或没有访问权限。",
            "建议：关闭占用该文件的程序后重试。",
        )
    if isinstance(exc, AuthenticationError):
        return (
            "处理失败：翻译接口认证失败。",
            "建议：请检查 .env 中的 LLM_API_KEY、LLM_BASE_URL 和 LLM_MODEL 是否正确。",
        )
    if isinstance(exc, RateLimitError):
        return (
            "处理失败：翻译接口请求过于频繁，或当前额度不足。",
            "建议：稍后重试，或检查 API 账户额度。",
        )
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return (
            "处理失败：无法连接翻译服务。",
            "建议：请检查当前网络，或稍后重试。",
        )
    if isinstance(exc, APIError):
        return (
            "处理失败：翻译服务暂时不可用。",
            "建议：请稍后重试。",
        )
    if isinstance(exc, (ValueError, RuntimeError, EnvironmentError)):
        return (f"处理失败：{exc}", None)
    return (
        "处理失败：程序遇到了未预期的问题。",
        "建议：请重试一次；如果问题持续存在，再把错误现象反馈出来。",
    )
