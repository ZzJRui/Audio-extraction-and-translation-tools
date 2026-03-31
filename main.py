from app_service import TRANSLATION_MODES, build_error_message, execute_subtitle_task
from config import AppConfig, get_app_root
from stability import collect_startup_report, format_startup_report, prepare_runtime_environment, write_task_diagnostic_log


def prompt_text(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip().strip('"').strip("'")
    return value or (default or "")


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


def print_startup_report(report_title: str, config: AppConfig, gui_backend: str, subtitle_mode: str | None = None) -> None:
    report = collect_startup_report(config, gui_backend=gui_backend, subtitle_mode=subtitle_mode)
    print(report_title)
    for line in format_startup_report(report):
        print(line)
    if report.has_fatal:
        raise RuntimeError("启动自检未通过，请先修复上面的 fatal 项。")


def run_app() -> None:
    project_root = get_app_root()
    prepare_runtime_environment(project_root)
    config = AppConfig()
    print_startup_report("启动自检结果：", config, gui_backend="cli")

    audio_path = prompt_text("音频路径", "input/audio.mp3")
    subtitle_mode = prompt_subtitle_mode()
    scene = prompt_scene_if_needed(subtitle_mode)

    config = AppConfig()
    report = collect_startup_report(config, gui_backend="cli", subtitle_mode=subtitle_mode)
    print("任务前检查：")
    for line in format_startup_report(report):
        print(line)
    if report.has_fatal:
        raise RuntimeError("任务前检查未通过，请先修复上面的 fatal 项。")

    try:
        result = execute_subtitle_task(
            project_root,
            config,
            audio_path,
            subtitle_mode,
            scene,
            progress_callback=print,
        )
    except Exception as exc:
        write_task_diagnostic_log(
            output_dir=config.output_dir,
            python_executable=report.python_executable,
            gui_backend="cli",
            audio_path=audio_path,
            subtitle_mode=subtitle_mode,
            startup_report=report,
            success=False,
            error_summary=f"{exc.__class__.__name__}: {exc}",
            config=config,
        )
        raise

    log_path = write_task_diagnostic_log(
        output_dir=result.output_dir,
        python_executable=report.python_executable,
        gui_backend="cli",
        audio_path=audio_path,
        subtitle_mode=subtitle_mode,
        startup_report=report,
        success=True,
        error_summary=None,
        config=config,
    )
    print(f"任务完成，诊断日志已写入：{log_path}")


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
