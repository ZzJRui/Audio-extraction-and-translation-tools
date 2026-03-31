import json
import subprocess
from pathlib import Path
from typing import Callable

PROGRESS_PREFIX = "__PROGRESS__:"
ProgressCallback = Callable[[str], None]


class BackendProcessError(RuntimeError):
    def __init__(self, stderr_text: str) -> None:
        self.stderr_text = stderr_text
        message = stderr_text.strip() or "后端返回了空错误信息。"
        super().__init__(message)


def _emit_progress(progress_callback: ProgressCallback | None, message: str) -> None:
    if progress_callback and message:
        progress_callback(message)


def run_backend_task(
    *,
    backend_python: str,
    backend_script: Path,
    app_root: Path,
    payload: dict,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    process = subprocess.Popen(
        [backend_python, str(backend_script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(app_root),
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    if process.stdin is None or process.stdout is None or process.stderr is None:
        raise RuntimeError("后端进程启动失败，无法建立通信通道。")

    process.stdin.write(json.dumps(payload, ensure_ascii=False))
    process.stdin.close()

    stderr_lines: list[str] = []
    while True:
        raw_line = process.stderr.readline()
        if raw_line == "":
            break

        line = raw_line.rstrip("\r\n")
        if line.startswith(PROGRESS_PREFIX):
            _emit_progress(progress_callback, line[len(PROGRESS_PREFIX) :].strip())
            continue
        if line:
            stderr_lines.append(line)

    return_code = process.wait()
    stdout_text = process.stdout.read().strip()
    stderr_text = "\n".join(stderr_lines).strip()

    if return_code != 0:
        raise BackendProcessError(stderr_text)
    if not stdout_text:
        raise BackendProcessError("后端未返回结果。")

    return json.loads(stdout_text)
