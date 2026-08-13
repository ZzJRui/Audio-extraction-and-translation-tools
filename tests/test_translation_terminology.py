import unittest
from types import SimpleNamespace
from unittest.mock import patch

from config import AppConfig
from transcribe import TranscriptSegment
from translate import build_translation_messages, translate_segments


class _FakeCompletions:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses

    def create(self, **kwargs):
        content = self._responses.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class _FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(responses))


class TranslationTerminologyTests(unittest.TestCase):
    def test_prompt_mentions_volleyball_context_terms(self) -> None:
        messages = build_translation_messages(
            "volleyball tutorial",
            [TranscriptSegment(index=1, start=0.0, end=1.0, text="the setter uses a quiet platform on float serve receive")],
        )

        self.assertIn("排球", messages[1]["content"])
        self.assertIn("局部明显不像自然英语", messages[1]["content"])
        self.assertIn("不得自由编造", messages[1]["content"])
        self.assertIn("passing", messages[1]["content"])
        self.assertIn("platform", messages[1]["content"])
        self.assertIn("midline", messages[1]["content"])
        self.assertIn("outside of the body", messages[1]["content"])
        self.assertIn("free ball", messages[1]["content"])
        self.assertIn("momentum", messages[1]["content"])
        self.assertIn("setter", messages[1]["content"])
        self.assertIn("float serve", messages[1]["content"])
        self.assertIn("serve receive", messages[1]["content"])

    def test_normalizes_common_volleyball_terms(self) -> None:
        config = AppConfig(
            llm_api_key="key",
            llm_base_url="https://example.invalid/v1",
            llm_model="test-model",
            translation_batch_size=1,
        )

        with patch(
            "translate.OpenAI",
            return_value=_FakeClient(
                ['{"items": [{"id": 1, "translation": "先练好发球接发球里的站立飘球，再练跳飘球，再让二传用手臂平台接一传。"}]}']
            ),
        ):
            translations = translate_segments(
                [TranscriptSegment(index=1, start=0.0, end=1.0, text="practice the float serves")],
                "volleyball tutorial",
                config,
            )

        self.assertEqual(translations, ["先练好接发球里的站飘发球，再练跳飘发球，再让二传用手臂平台接一传。"])


if __name__ == "__main__":
    unittest.main()
