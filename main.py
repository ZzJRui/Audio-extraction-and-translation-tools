from config import AppConfig, get_app_root, save_env_value
from app_service import (
    TRANSLATION_MODES,
    build_error_message,
    execute_subtitle_task,
    initialize_runtime,
    prepare_task_dirs,
)


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


def prompt_scene_if_needed(subtitle_mode: str) -> str | None:
    if subtitle_mode == "original":
        print("已选择原文字幕，跳过翻译情景输入。")
        return None
    return prompt_text("翻译情景", "日常对话")


def prompt_api_key_if_needed(subtitle_mode: str, config: AppConfig) -> AppConfig:
    if subtitle_mode in TRANSLATION_MODES and not config.llm_api_key:
        api_key = prompt_secret("请输入 LLM_API_KEY")
        save_env_value("LLM_API_KEY", api_key)
        return AppConfig()
    return config


def run_app() -> None:
    project_root = get_app_root()
    config = AppConfig()
    initialize_runtime(project_root, config)
    prepare_task_dirs(
        project_root,
        config.output_dir,
        clear_input=True,
        clear_output=True,
        progress_callback=print,
    )

    audio_path = prompt_text("音频路径", "input/audio.mp3")
    subtitle_mode = prompt_subtitle_mode()
    config = prompt_api_key_if_needed(subtitle_mode, config)
    scene = prompt_scene_if_needed(subtitle_mode)

    execute_subtitle_task(
        project_root,
        config,
        audio_path,
        subtitle_mode,
        scene,
        progress_callback=print,
    )


def main() -> None:
    try:
        run_app()
    except KeyboardInterrupt:
        print("\n已取消操作。")
        raise SystemExit(1)
    except Exception as exc:
        message, suggestion = build_error_message(exc)
        print(message)
        if suggestion:
            print(suggestion)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
