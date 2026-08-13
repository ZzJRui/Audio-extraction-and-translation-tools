import json
import shutil
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from config import AppConfig
from stability import collect_startup_report, should_warn_about_model_download, write_task_diagnostic_log


@contextmanager
def workspace_tempdir():
    root = Path.cwd() / ".tmp_test" / f"stability-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


class StartupReportTests(unittest.TestCase):
    def test_ffmpeg_missing_is_fatal(self) -> None:
        config = AppConfig(output_dir_name=".tmp_test/stability-output")
        with patch("stability.shutil.which", return_value=None):
            report = collect_startup_report(config, gui_backend="pyside6")
        self.assertTrue(report.has_fatal)
        self.assertIn("ffmpeg_missing", [item.code for item in report.items if item.level == "fatal"])

    def test_translation_mode_requires_llm_settings(self) -> None:
        config = AppConfig(llm_api_key="", llm_base_url="", llm_model="", output_dir_name=".tmp_test/stability-output")
        with patch("stability.shutil.which", return_value="ffmpeg"):
            report = collect_startup_report(config, gui_backend="pyside6", subtitle_mode="translation")
        fatal_codes = [item.code for item in report.items if item.level == "fatal"]
        self.assertIn("llm_api_key_missing", fatal_codes)
        self.assertIn("llm_base_url_missing", fatal_codes)
        self.assertIn("llm_model_missing", fatal_codes)

    def test_original_mode_does_not_require_llm_settings(self) -> None:
        config = AppConfig(llm_api_key="", llm_base_url="", llm_model="", output_dir_name=".tmp_test/stability-output")
        with patch("stability.shutil.which", return_value="ffmpeg"):
            report = collect_startup_report(config, gui_backend="pyside6", subtitle_mode="original")
        fatal_codes = [item.code for item in report.items if item.level == "fatal"]
        self.assertNotIn("llm_api_key_missing", fatal_codes)
        self.assertNotIn("llm_base_url_missing", fatal_codes)
        self.assertNotIn("llm_model_missing", fatal_codes)

    def test_tiny_model_adds_quality_warning(self) -> None:
        config = AppConfig(whisper_model_size="tiny", output_dir_name=".tmp_test/stability-output")
        with patch("stability.shutil.which", return_value="ffmpeg"):
            report = collect_startup_report(config, gui_backend="pyside6", subtitle_mode="original")
        warning_codes = [item.code for item in report.items if item.level == "warning"]
        self.assertIn("whisper_tiny_quality", warning_codes)

    def test_unset_source_language_defaults_to_english_context(self) -> None:
        config = AppConfig(source_language=None, output_dir_name=".tmp_test/stability-output")
        with patch("stability.shutil.which", return_value="ffmpeg"):
            report = collect_startup_report(config, gui_backend="pyside6", subtitle_mode="original")
        info_codes = [item.code for item in report.items if item.level == "info"]
        warning_codes = [item.code for item in report.items if item.level == "warning"]
        self.assertIn("source_language_defaulted", info_codes)
        self.assertNotIn("source_language_auto_detect", warning_codes)


class DiagnosticLogTests(unittest.TestCase):
    def test_task_diagnostic_log_redacts_api_key_and_records_asr_runtime(self) -> None:
        with workspace_tempdir() as output_dir:
            config = AppConfig(
                llm_api_key="super-secret-key",
                llm_base_url="https://example.invalid/v1",
                llm_model="test-model",
                output_dir_name=str(output_dir),
            )
            with patch("stability.shutil.which", return_value="ffmpeg"):
                report = collect_startup_report(config, gui_backend="pyside6", subtitle_mode="translation")
            log_path = write_task_diagnostic_log(
                output_dir=output_dir,
                python_executable="python.exe",
                gui_backend="pyside6",
                audio_path="demo.wav",
                subtitle_mode="translation",
                startup_report=report,
                success=False,
                error_summary="AuthenticationError: invalid api key",
                config=config,
            )
            payload = json.loads(log_path.read_text(encoding="utf-8"))
        self.assertTrue(log_path.name.endswith(".json"))
        self.assertTrue(payload["config"]["llm_api_key_configured"])
        self.assertEqual(payload["config"]["effective_source_language"], "en")
        self.assertEqual(payload["config"]["whisper_beam_size"], 5)
        self.assertTrue(payload["config"]["whisper_word_timestamps"])
        self.assertNotIn("super-secret-key", json.dumps(payload, ensure_ascii=False))


class WhisperCacheHintTests(unittest.TestCase):
    def test_warns_when_model_cache_is_missing(self) -> None:
        with workspace_tempdir() as hf_home:
            config = AppConfig(whisper_model_size="tiny")
            with patch.dict("os.environ", {"HF_HOME": str(hf_home)}, clear=False):
                self.assertTrue(should_warn_about_model_download(config))

    def test_does_not_warn_when_model_cache_exists(self) -> None:
        with workspace_tempdir() as hf_home:
            snapshot_dir = hf_home / "hub" / "models--Systran--faster-whisper-tiny" / "snapshots" / "abc123"
            snapshot_dir.mkdir(parents=True)
            config = AppConfig(whisper_model_size="tiny")
            with patch.dict("os.environ", {"HF_HOME": str(hf_home)}, clear=False):
                self.assertFalse(should_warn_about_model_download(config))


if __name__ == "__main__":
    unittest.main()
