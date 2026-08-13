import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import srt

from app_service import execute_subtitle_task
from config import AppConfig
from subtitle import format_translation_text, normalize_segments
from transcribe import TranscriptSegment
from translate import build_translation_messages


class SubtitleFormattingTests(unittest.TestCase):
    def test_removes_terminal_punctuation_when_it_would_be_alone(self) -> None:
        text = ("这" * 19) + "。"

        formatted = format_translation_text(text)

        self.assertEqual(formatted, "这" * 19)
        self.assertNotIn("\n。", formatted)

    def test_keeps_middle_punctuation_when_breaking_lines(self) -> None:
        text = ("这" * 17) + "。" + "后面还有内容"

        formatted = format_translation_text(text)

        self.assertIn("。\n", formatted)
        self.assertTrue(formatted.endswith("后面还有内容"))


class SubtitleNormalizationTests(unittest.TestCase):
    def test_splits_long_chinese_segment_and_preserves_duration(self) -> None:
        original = TranscriptSegment(
            index=1,
            start=2.0,
            end=10.0,
            text="第一句内容比较长，第二句内容也比较长。第三句继续补充一些信息。",
        )

        normalized = normalize_segments([original])

        self.assertGreater(len(normalized), 1)
        self.assertEqual(normalized[0].start, original.start)
        self.assertEqual(normalized[-1].end, original.end)
        self.assertEqual("".join(segment.text for segment in normalized), original.text)
        self.assertEqual([segment.index for segment in normalized], [1, 2, 3])

        for previous, current in zip(normalized, normalized[1:]):
            self.assertLess(previous.start, previous.end)
            self.assertEqual(previous.end, current.start)

    def test_falls_back_to_safe_split_without_punctuation(self) -> None:
        original = TranscriptSegment(
            index=1,
            start=0.0,
            end=9.0,
            text="this is a very long subtitle segment without any punctuation or pauses at all",
        )

        normalized = normalize_segments([original])

        self.assertGreater(len(normalized), 1)
        self.assertEqual(
            " ".join(segment.text for segment in normalized),
            " ".join(original.text.split()),
        )
        self.assertEqual(normalized[-1].end, original.end)


class SubtitlePipelineTests(unittest.TestCase):
    def test_execute_task_translates_normalized_segments_before_building_bilingual_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            audio_path = project_root / "sample.wav"
            output_dir = project_root / "generated"
            audio_path.write_bytes(b"fake audio")

            raw_segments = [
                TranscriptSegment(
                    index=1,
                    start=0.0,
                    end=8.0,
                    text=(
                        "Step 1 keeps your platform quiet during contact. "
                        "Step 2 sends the ball forward with your legs. "
                        "Step 3 holds the finish to guide the pass."
                    ),
                )
            ]
            normalized_segments = normalize_segments(raw_segments)

            def fake_translate(
                segments: list[TranscriptSegment],
                scene: str,
                config: AppConfig,
            ) -> list[str]:
                self.assertEqual(scene, "日常对话")
                self.assertEqual(segments, normalized_segments)
                return [f"第{index}段译文：{segment.text}" for index, segment in enumerate(segments, start=1)]

            config = AppConfig(
                llm_api_key="key",
                llm_base_url="https://example.invalid/v1",
                llm_model="test-model",
                output_dir_name=str(output_dir),
            )

            with (
                patch("app_service.initialize_runtime"),
                patch("app_service.transcribe_audio", return_value=raw_segments),
                patch("app_service.translate_segments", side_effect=fake_translate),
            ):
                result = execute_subtitle_task(
                    project_root=project_root,
                    config=config,
                    audio_path=audio_path,
                    subtitle_mode="bilingual",
                    scene="日常对话",
                )

            subtitles = list(srt.parse(result.output_file.read_text(encoding="utf-8")))
            self.assertEqual(result.segment_count, len(normalized_segments))
            self.assertEqual(result.raw_segment_count, len(raw_segments))
            self.assertEqual(len(subtitles), len(normalized_segments))

            for subtitle, segment in zip(subtitles, normalized_segments, strict=True):
                self.assertEqual(subtitle.start.total_seconds(), segment.start)
                self.assertEqual(subtitle.end.total_seconds(), segment.end)
                self.assertIn(segment.text, subtitle.content)

    def test_execute_task_translation_mode_uses_normalized_segments_for_one_to_one_cues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            audio_path = project_root / "sample.wav"
            output_dir = project_root / "generated"
            audio_path.write_bytes(b"fake audio")

            raw_segments = [
                TranscriptSegment(
                    index=1,
                    start=2.0,
                    end=14.0,
                    text=(
                        "Step 1 keeps the base under you. "
                        "Step 2 meets the ball in front of your hips. "
                        "Step 3 freezes the angle after contact."
                    ),
                )
            ]
            normalized_segments = normalize_segments(raw_segments)

            config = AppConfig(
                llm_api_key="key",
                llm_base_url="https://example.invalid/v1",
                llm_model="test-model",
                output_dir_name=str(output_dir),
            )

            with (
                patch("app_service.initialize_runtime"),
                patch("app_service.transcribe_audio", return_value=raw_segments),
                patch(
                    "app_service.translate_segments",
                    side_effect=lambda segments, *_: [
                        f"第{index}段译文：{segment.text}" for index, segment in enumerate(segments, start=1)
                    ],
                ),
            ):
                result = execute_subtitle_task(
                    project_root=project_root,
                    config=config,
                    audio_path=audio_path,
                    subtitle_mode="translation",
                    scene="排球教学",
                )

            subtitles = list(srt.parse(result.output_file.read_text(encoding="utf-8")))
            self.assertEqual(result.segment_count, len(normalized_segments))
            self.assertEqual(result.raw_segment_count, len(raw_segments))
            self.assertEqual(len(subtitles), len(normalized_segments))

            for subtitle, segment in zip(subtitles, normalized_segments, strict=True):
                self.assertEqual(subtitle.start.total_seconds(), segment.start)
                self.assertEqual(subtitle.end.total_seconds(), segment.end)
                self.assertIn(segment.text, subtitle.content)


class TranslationPromptTests(unittest.TestCase):
    def test_translation_messages_include_context_and_accuracy_rules(self) -> None:
        batch = [
            TranscriptSegment(index=1, start=0.0, end=1.0, text="How did that happen?"),
            TranscriptSegment(index=2, start=1.0, end=2.0, text="I have no idea."),
        ]

        messages = build_translation_messages("排球教学", batch)

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("合法 JSON", messages[0]["content"])
        self.assertIn("字幕翻译", messages[1]["content"])
        self.assertIn("结合上下文", messages[1]["content"])
        self.assertIn("不得漏译", messages[1]["content"])
        self.assertIn("排球教学", messages[1]["content"])
        self.assertIn("体育语境", messages[1]["content"])
        self.assertIn('"id": 1', messages[1]["content"])
        self.assertIn("每个 id 都必须单独翻译", messages[1]["content"])
        self.assertIn("不得跨条目合并", messages[1]["content"])
        self.assertIn("不得把一个条目的内容拆给别的条目", messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
