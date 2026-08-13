import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DocumentationContractTests(unittest.TestCase):
    def test_readme_documents_stability_contract(self) -> None:
        content = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("Python 3.13", content)
        self.assertIn("Tkinter", content)
        self.assertIn("ffmpeg", content)
        self.assertIn("启动自检", content)

    def test_agent_documents_stability_contract(self) -> None:
        content = (PROJECT_ROOT / "AGENT.md").read_text(encoding="utf-8")

        self.assertIn("Python 后端", content)
        self.assertIn("启动自检", content)
        self.assertIn("Tkinter", content)
        self.assertIn("README", content)


if __name__ == "__main__":
    unittest.main()
