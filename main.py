from pathlib import Path
import shutil
import os

from config import AppConfig, save_env_value
from subtitle import (
    build_bilingual_subtitles,
    build_original_subtitles,
    build_translation_subtitles,
    write_srt_file,
)
from transcribe import transcribe_audio
from translate import translate_segments


def prompt_text(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip().strip('"').strip("'")
    return value or (default or "")


def prompt_secret(label: str) -> str:
    value = input(f"{label}: ").strip()
    if not value:
        raise ValueError(f"{label} 不能为空。")
    return value


def prompt_subtitle_mode() -> str:
    print("请选择字幕输出类型：")
    print("1. 原文字幕")
    print("2. 译文字幕")
    print("3. 双语字幕")

    mapping = {
        "1": "original",
        "2": "translation",
        "3": "bilingual",
    }

    while True:
        choice = input("请输入数字 [1/2/3]: ").strip()
        mode = mapping.get(choice)
        if mode:
            return mode
        print("输入无效，请输入 1、2 或 3。")


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


def prepare_task_dirs(project_root: Path, output_dir: Path) -> None:
    input_dir = project_root / "input"
    print("正在清理上一轮任务留下的输入和输出文件...")
    clear_directory_files(input_dir)
    clear_directory_files(output_dir)
    print("清理完成。")


def configure_local_ffmpeg(project_root: Path) -> None:
    ffmpeg_root = project_root / "tools" / "ffmpeg"
    for ffmpeg_exe in ffmpeg_root.rglob("ffmpeg.exe"):
        bin_dir = ffmpeg_exe.parent
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        break


def configure_runtime_env() -> None:
    # Work around duplicate OpenMP runtime loading on some Windows Python setups.
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


def validate_runtime(config: AppConfig) -> None:
    if shutil.which("ffmpeg") is None:
        raise EnvironmentError("未检测到 ffmpeg，请先安装并加入系统 PATH。")


def main() -> None:
    project_root = Path(__file__).resolve().parent
    configure_runtime_env()
    configure_local_ffmpeg(project_root)
    config = AppConfig()
    validate_runtime(config)

    output_dir = config.output_dir
    prepare_task_dirs(project_root, output_dir)

    if not config.llm_api_key:
        api_key = prompt_secret("请输入 LLM_API_KEY")
        save_env_value("LLM_API_KEY", api_key)
        config = AppConfig()

    audio_path = prompt_text("音频路径", "input/audio.mp3")
    scene = prompt_text("翻译情景", "日常对话")
    subtitle_mode = prompt_subtitle_mode()

    ensure_output_dir(output_dir)

    print("1/3 正在进行语音识别...")
    segments = transcribe_audio(audio_path, config)
    print(f"识别完成，共 {len(segments)} 条片段。")

    translations: list[str] | None = None
    if subtitle_mode in {"translation", "bilingual"}:
        print("2/3 正在进行情景翻译...")
        translations = translate_segments(segments, scene, config)
        print("翻译完成。")
    else:
        print("2/3 已跳过翻译，当前仅输出原文字幕。")

    print("3/3 正在生成字幕文件...")
    if subtitle_mode == "original":
        write_srt_file(output_dir / "original.srt", build_original_subtitles(segments))
        print("已生成: original.srt")
    elif subtitle_mode == "translation":
        write_srt_file(
            output_dir / "translation.srt",
            build_translation_subtitles(segments, translations or []),
        )
        print("已生成: translation.srt")
    else:
        write_srt_file(
            output_dir / "bilingual.srt",
            build_bilingual_subtitles(segments, translations or []),
        )
        print("已生成: bilingual.srt")

    print(f"已输出到目录: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
