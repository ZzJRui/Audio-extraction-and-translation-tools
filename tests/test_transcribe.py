import shutil
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from config import AppConfig
from transcribe import transcribe_audio


@contextmanager
def workspace_tempdir():
    root = Path.cwd() / ".tmp_test" / f"transcribe-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


class TranscribeAudioTests(unittest.TestCase):
    def test_transcribe_audio_prefers_explicit_source_language_and_enables_word_timestamps(self) -> None:
        with workspace_tempdir() as temp_dir:
            audio_path = temp_dir / "sample.wav"
            audio_path.write_bytes(b"fake audio")

            fake_model = Mock()
            fake_model.transcribe.return_value = (
                [SimpleNamespace(start=0.0, end=1.5, text=" hello world ")],
                {"language": "fr"},
            )

            config = AppConfig(
                whisper_model_size="small",
                whisper_device="cpu",
                whisper_compute_type="int8",
                source_language="en",
            )

            with patch("transcribe.WhisperModel", return_value=fake_model) as model_cls:
                result = transcribe_audio(audio_path, config)

        model_cls.assert_called_once_with(
            model_size_or_path="small",
            device="cpu",
            compute_type="int8",
        )
        fake_model.transcribe.assert_called_once()
        kwargs = fake_model.transcribe.call_args.kwargs
        self.assertEqual(kwargs["language"], "en")
        self.assertTrue(kwargs["word_timestamps"])
        self.assertEqual(result[0].text, "hello world")

    def test_transcribe_audio_defaults_blank_source_language_to_english(self) -> None:
        with workspace_tempdir() as temp_dir:
            audio_path = temp_dir / "sample.wav"
            audio_path.write_bytes(b"fake audio")

            fake_model = Mock()
            fake_model.transcribe.return_value = (
                [SimpleNamespace(start=0.0, end=1.0, text=" test ")],
                {"language": "en"},
            )

            config = AppConfig(source_language="   ")

            with patch("transcribe.WhisperModel", return_value=fake_model):
                transcribe_audio(audio_path, config)

        kwargs = fake_model.transcribe.call_args.kwargs
        self.assertEqual(kwargs["language"], "en")
        self.assertTrue(kwargs["word_timestamps"])

    def test_transcribe_audio_preserves_word_timings_when_available(self) -> None:
        with workspace_tempdir() as temp_dir:
            audio_path = temp_dir / "sample.wav"
            audio_path.write_bytes(b"fake audio")

            fake_model = Mock()
            fake_model.transcribe.return_value = (
                [
                    SimpleNamespace(
                        start=0.0,
                        end=1.0,
                        text=" move your feet ",
                        words=[
                            SimpleNamespace(start=0.0, end=0.25, word=" move"),
                            SimpleNamespace(start=0.25, end=0.55, word=" your"),
                            SimpleNamespace(start=0.55, end=1.0, word=" feet"),
                        ],
                    )
                ],
                {"language": "en"},
            )

            with patch("transcribe.WhisperModel", return_value=fake_model):
                result = transcribe_audio(audio_path, AppConfig(source_language=""))

        self.assertEqual([word.text for word in result[0].words], ["move", "your", "feet"])
        self.assertEqual(result[0].words[0].start, 0.0)
        self.assertEqual(result[0].words[-1].end, 1.0)


if __name__ == "__main__":
    unittest.main()
