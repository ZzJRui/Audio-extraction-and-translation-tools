import json
import sys
from dataclasses import asdict
from pathlib import Path

from app_service import execute_subtitle_task
from config import AppConfig, get_app_root


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        audio_path = payload["audio_path"]
        subtitle_mode = payload["subtitle_mode"]
        scene = payload.get("scene")

        config = AppConfig()
        result = execute_subtitle_task(
            get_app_root(),
            config,
            audio_path,
            subtitle_mode,
            scene,
        )

        response = asdict(result)
        response["output_file"] = str(Path(result.output_file).resolve())
        response["output_dir"] = str(Path(result.output_dir).resolve())
        json.dump(response, sys.stdout, ensure_ascii=False)
        return 0
    except Exception as exc:
        print(f"{exc.__class__.__name__}:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
