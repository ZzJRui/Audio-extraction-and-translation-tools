import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import backend_client
import backend_runner
from app_service import TaskResult


PROGRESS_ONE = "1/3 \u6b63\u5728\u8fdb\u884c\u8bed\u97f3\u8bc6\u522b..."
PROGRESS_TWO = "3/3 \u6b63\u5728\u751f\u6210\u5b57\u5e55\u6587\u4ef6..."


class _FakeStream:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def readline(self) -> str:
        if self._lines:
            return self._lines.pop(0)
        return ""

    def read(self) -> str:
        if not self._lines:
            return ""
        remaining = "".join(self._lines)
        self._lines.clear()
        return remaining


class _FakePopen:
    def __init__(self, stdout_lines: list[str], stderr_lines: list[str], returncode: int = 0) -> None:
        self.stdin = io.StringIO()
        self.stdout = _FakeStream(stdout_lines)
        self.stderr = _FakeStream(stderr_lines)
        self.returncode = returncode

    def wait(self) -> int:
        return self.returncode


class BackendProgressTests(unittest.TestCase):
    def test_backend_runner_emits_progress_lines_before_result_json(self) -> None:
        payload = {"audio_path": "demo.wav", "subtitle_mode": "original", "scene": None}
        result = TaskResult(
            subtitle_mode="original",
            output_file=Path("output/original.srt"),
            output_dir=Path("output"),
            segment_count=1,
            used_translation=False,
            preview_text="preview",
        )
        report = SimpleNamespace(has_fatal=False, python_executable="python.exe", items=())

        def fake_execute(*args, **kwargs):
            kwargs["progress_callback"](PROGRESS_ONE)
            kwargs["progress_callback"](PROGRESS_TWO)
            return result

        with (
            patch("backend_runner.execute_subtitle_task", side_effect=fake_execute),
            patch("backend_runner.collect_startup_report", return_value=report),
            patch("backend_runner.write_task_diagnostic_log"),
            patch("backend_runner.AppConfig"),
            patch("backend_runner.get_app_root", return_value=Path(".")),
            patch("sys.stdin", io.StringIO(json.dumps(payload))),
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
            patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            exit_code = backend_runner.main()

        self.assertEqual(exit_code, 0)
        self.assertIn(f"__PROGRESS__:{PROGRESS_ONE}", stderr.getvalue())
        self.assertIn(f"__PROGRESS__:{PROGRESS_TWO}", stderr.getvalue())
        response = json.loads(stdout.getvalue())
        self.assertEqual(response["output_file"], str(Path("output/original.srt").resolve()))


class BackendClientProgressTests(unittest.TestCase):
    def test_backend_client_streams_progress_while_task_is_running(self) -> None:
        result_payload = {
            "output_file": str(Path("output/original.srt").resolve()),
            "output_dir": str(Path("output").resolve()),
            "subtitle_mode": "original",
            "segment_count": 1,
            "used_translation": False,
            "preview_text": "preview",
        }
        process = _FakePopen(
            stdout_lines=[json.dumps(result_payload, ensure_ascii=False)],
            stderr_lines=[
                f"__PROGRESS__:{PROGRESS_ONE}\n",
                f"__PROGRESS__:{PROGRESS_TWO}\n",
                "",
            ],
        )

        progress_messages: list[str] = []
        payload = {"audio_path": "demo.wav", "subtitle_mode": "original", "scene": None}
        with (
            patch("backend_client.subprocess.run", side_effect=AssertionError("expected streaming backend process")),
            patch("backend_client.subprocess.Popen", return_value=process),
        ):
            result = backend_client.run_backend_task(
                backend_python="python",
                backend_script=Path("backend_runner.py"),
                app_root=Path("."),
                payload=payload,
                progress_callback=progress_messages.append,
            )

        self.assertIn(PROGRESS_ONE, progress_messages)
        self.assertIn(PROGRESS_TWO, progress_messages)
        self.assertEqual(result["output_file"], result_payload["output_file"])


if __name__ == "__main__":
    unittest.main()
