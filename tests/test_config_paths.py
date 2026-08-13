import os
import shutil
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from config import AppConfig, get_bundle_root, get_data_root, get_env_file_path, get_env_template_path, get_runtime_root, load_dotenv


@contextmanager
def workspace_tempdir():
    root = Path.cwd() / ".tmp_test" / f"config-paths-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


class ConfigPathTests(unittest.TestCase):
    def test_explicit_bundle_data_and_runtime_roots_are_used(self) -> None:
        with workspace_tempdir() as root:
            bundle_root = root / "bundle"
            data_root = root / "data"
            runtime_root = data_root / "runtime"
            bundle_root.mkdir(parents=True)
            data_root.mkdir(parents=True)
            runtime_root.mkdir(parents=True)

            with patch.dict(
                os.environ,
                {
                    "APP_BUNDLE_ROOT": str(bundle_root),
                    "APP_DATA_ROOT": str(data_root),
                    "APP_RUNTIME_ROOT": str(runtime_root),
                },
                clear=False,
            ):
                self.assertEqual(get_bundle_root(), bundle_root)
                self.assertEqual(get_data_root(), data_root)
                self.assertEqual(get_runtime_root(), runtime_root)
                self.assertEqual(get_env_file_path(), data_root / ".env")
                self.assertEqual(get_env_template_path(), bundle_root / ".env.example")

    def test_load_dotenv_reads_from_data_root_by_default(self) -> None:
        with workspace_tempdir() as root:
            bundle_root = root / "bundle"
            data_root = root / "data"
            bundle_root.mkdir(parents=True)
            data_root.mkdir(parents=True)
            (bundle_root / ".env").write_text("LLM_MODEL=bundle-model\n", encoding="utf-8")
            (data_root / ".env").write_text("LLM_MODEL=data-model\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "APP_BUNDLE_ROOT": str(bundle_root),
                    "APP_DATA_ROOT": str(data_root),
                },
                clear=False,
            ):
                with patch.dict(os.environ, {}, clear=True):
                    os.environ["APP_BUNDLE_ROOT"] = str(bundle_root)
                    os.environ["APP_DATA_ROOT"] = str(data_root)
                    load_dotenv()
                    self.assertEqual(os.environ.get("LLM_MODEL"), "data-model")

    def test_output_dir_defaults_to_data_root(self) -> None:
        with workspace_tempdir() as root:
            data_root = root / "data"
            data_root.mkdir(parents=True)
            with patch.dict(os.environ, {"APP_DATA_ROOT": str(data_root)}, clear=False):
                config = AppConfig(output_dir_name="output")
                self.assertEqual(config.output_dir, data_root / "output")


if __name__ == "__main__":
    unittest.main()
