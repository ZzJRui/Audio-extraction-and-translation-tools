import unittest
from pathlib import Path

import srt

from subtitle import build_translation_subtitles, write_srt_file
from transcribe import TranscriptSegment
from translate import build_translation_messages


class SurrogateSanitizationTests(unittest.TestCase):
    def test_write_srt_file_replaces_lone_surrogates(self) -> None:
        subtitles = build_translation_subtitles(
            [TranscriptSegment(index=1, start=0.0, end=1.0, text="hello")],
            ["bad\udcadtext"],
        )

        output_dir = Path('.tmp_test')
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / 'translation-surrogate-test.srt'
        if output_path.exists():
            output_path.unlink()

        write_srt_file(output_path, subtitles)

        written = output_path.read_text(encoding='utf-8')
        parsed = list(srt.parse(written))
        self.assertEqual(parsed[0].content, 'bad?text')

    def test_translation_messages_are_utf8_encodable_when_segment_contains_surrogate(self) -> None:
        messages = build_translation_messages(
            'scene\udcad',
            [TranscriptSegment(index=1, start=0.0, end=1.0, text='hello\udcadworld')],
        )

        for message in messages:
            message['content'].encode('utf-8')

    def test_execute_task_succeeds_when_transcript_contains_surrogate(self) -> None:
        from unittest.mock import patch

        from app_service import execute_subtitle_task
        from config import AppConfig

        output_dir = Path('.tmp_test') / 'surrogate-pipeline-output'
        output_dir.mkdir(parents=True, exist_ok=True)
        audio_path = Path('.tmp_test') / 'surrogate-pipeline.wav'
        audio_path.write_bytes(b'fake audio')

        raw_segments = [TranscriptSegment(index=1, start=0.0, end=1.0, text='hello\udcadworld')]

        config = AppConfig(
            llm_api_key='key',
            llm_base_url='https://example.invalid/v1',
            llm_model='test-model',
            output_dir_name=str(output_dir),
        )

        with (
            patch('app_service.initialize_runtime'),
            patch('app_service.transcribe_audio', return_value=raw_segments),
            patch('app_service.translate_segments', return_value=['good\udcadtranslation']),
        ):
            result = execute_subtitle_task(
                project_root=Path('.'),
                config=config,
                audio_path=audio_path,
                subtitle_mode='bilingual',
                scene='scene\udcad',
            )

        self.assertIn('good?translation', result.preview_text)
        self.assertIn('hello?world', result.preview_text)


if __name__ == '__main__':
    unittest.main()
