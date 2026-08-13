import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class PySide6RuntimeTests(unittest.TestCase):
    def test_gui_prefers_working_conda_pyside6_runtime(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", "import gui; print(gui.GUI_BACKEND)"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "pyside6")

    def test_main_window_can_be_created_with_pyside6(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import gui; "
                    "from PySide6.QtWidgets import QApplication; "
                    "app = QApplication([]); "
                    "window = gui.MainWindow(); "
                    "print(gui.GUI_BACKEND); "
                    "print(type(window).__name__)"
                ),
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["pyside6", "MainWindow"])


if __name__ == "__main__":
    unittest.main()
