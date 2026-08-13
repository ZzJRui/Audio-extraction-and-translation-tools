import unittest
from types import SimpleNamespace
from unittest.mock import patch

from config import AppConfig
from transcribe import TranscriptSegment
from translate import translate_segments


class _FakeCompletions:
    def __init__(self, responses: list[str], call_messages: list[list[dict[str, str]]]) -> None:
        self._responses = responses
        self._call_messages = call_messages

    def create(self, **kwargs):
        self._call_messages.append(kwargs["messages"])
        content = self._responses.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class _FakeClient:
    def __init__(self, responses: list[str], call_messages: list[list[dict[str, str]]]) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(responses, call_messages))


class TranslationRetryTests(unittest.TestCase):
    def test_retries_missing_items_and_only_requests_missing_ids(self) -> None:
        segments = [
            TranscriptSegment(index=1, start=0.0, end=1.0, text="A"),
            TranscriptSegment(index=2, start=1.0, end=2.0, text="B"),
            TranscriptSegment(index=3, start=2.0, end=3.0, text="C"),
        ]
        responses = [
            '{"items": [{"id": 1, "translation": "T1"}, {"id": 2, "translation": "T2"}]}',
            '{"items": [{"id": 3, "translation": "T3"}]}',
        ]
        call_messages: list[list[dict[str, str]]] = []

        config = AppConfig(
            llm_api_key="key",
            llm_base_url="https://example.invalid/v1",
            llm_model="test-model",
            translation_batch_size=3,
        )

        with patch("translate.OpenAI", return_value=_FakeClient(responses, call_messages)):
            translations = translate_segments(segments, "scene", config)

        self.assertEqual(translations, ["T1", "T2", "T3"])
        self.assertEqual(len(call_messages), 2)

        first_user_message = call_messages[0][1]["content"]
        second_user_message = call_messages[1][1]["content"]
        first_payload = first_user_message.split("待翻译内容：", maxsplit=1)[-1]
        second_payload = second_user_message.split("待翻译内容：", maxsplit=1)[-1]
        self.assertIn('"id": 1', first_payload)
        self.assertIn('"id": 2', first_payload)
        self.assertIn('"id": 3', first_payload)
        self.assertNotIn('"id": 1', second_payload)
        self.assertNotIn('"id": 2', second_payload)
        self.assertIn('"id": 3', second_payload)


if __name__ == "__main__":
    unittest.main()

