import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class GuiStartupTests(unittest.TestCase):
    def test_gui_module_import_does_not_crash_without_qt_runtime(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", "import gui; print(getattr(gui, 'GUI_BACKEND', 'missing'))"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn(result.stdout.strip(), {"pyside6", "tkinter"})


class LauncherScriptTests(unittest.TestCase):
    def test_run_gui_bat_has_no_machine_specific_paths(self) -> None:
        content = (PROJECT_ROOT / "run_gui.bat").read_text(encoding="utf-8")

        self.assertNotIn("C:\\Users\\zzz\\", content)


if __name__ == "__main__":
    unittest.main()
