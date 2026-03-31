import json
import sys
from dataclasses import asdict
from pathlib import Path

from app_service import execute_subtitle_task
from backend_client import PROGRESS_PREFIX
from config import AppConfig, get_app_root
from stability import collect_startup_report, prepare_runtime_environment, write_task_diagnostic_log
from text_safety import sanitize_utf8_text


def main() -> int:
    report = None
    config = AppConfig()
    audio_path = ""
    subtitle_mode = "original"
    gui_backend = "pyside6"
    try:
        payload = json.load(sys.stdin)
        audio_path = payload["audio_path"]
        subtitle_mode = payload["subtitle_mode"]
        scene = payload.get("scene")
        gui_backend = payload.get("gui_backend", "pyside6")
        app_root = get_app_root()

        prepare_runtime_environment(app_root)
        config = AppConfig()
        report = collect_startup_report(config, gui_backend=gui_backend, subtitle_mode=subtitle_mode)
        if report.has_fatal:
            fatal_messages = [item.message for item in report.items if item.level == "fatal"]
            raise RuntimeError("；".join(fatal_messages))

        result = execute_subtitle_task(
            app_root,
            config,
            audio_path,
            subtitle_mode,
            scene,
            progress_callback=lambda message: print(
                f"{PROGRESS_PREFIX}{sanitize_utf8_text(message)}",
                file=sys.stderr,
                flush=True,
            ),
        )

        response = asdict(result)
        response["output_file"] = str(Path(result.output_file).resolve())
        response["output_dir"] = str(Path(result.output_dir).resolve())
        write_task_diagnostic_log(
            output_dir=result.output_dir,
            python_executable=(report.python_executable if report else sys.executable),
            gui_backend=gui_backend,
            audio_path=audio_path,
            subtitle_mode=subtitle_mode,
            startup_report=report or collect_startup_report(config, gui_backend=gui_backend),
            success=True,
            error_summary=None,
            config=config,
        )
        json.dump(response, sys.stdout, ensure_ascii=False)
        return 0
    except Exception as exc:
        try:
            write_task_diagnostic_log(
                output_dir=config.output_dir,
                python_executable=(report.python_executable if report else sys.executable),
                gui_backend=gui_backend,
                audio_path=audio_path,
                subtitle_mode=subtitle_mode,
                startup_report=report or collect_startup_report(config, gui_backend=gui_backend),
                success=False,
                error_summary=f"{exc.__class__.__name__}: {exc}",
                config=config,
            )
        except Exception:
            pass
        print(sanitize_utf8_text(f"{exc.__class__.__name__}:{exc}"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
