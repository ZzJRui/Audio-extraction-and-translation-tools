import re
import unittest

from subtitle import (
    SubtitleSettings,
    build_bilingual_subtitles,
    build_translation_subtitles,
    normalize_segments,
)
from transcribe import TranscriptSegment, TranscriptWord
from translate import build_translation_messages


class SubtitleReadabilityTests(unittest.TestCase):
    def _split_bilingual_blocks(self, content: str) -> tuple[str, str]:
        lines = content.splitlines()
        translation_lines = [line for line in lines if re.search(r"[\u4e00-\u9fff]", line)]
        original_lines = [line for line in lines if re.search(r"[A-Za-z]", line)]
        return "\n".join(translation_lines), "\n".join(original_lines)

    def _extract_original_lines(self, content: str) -> list[str]:
        return [line for line in content.splitlines() if re.search(r"[A-Za-z]", line)]

    def _assert_no_bad_english_breaks(self, subtitles, forbidden_suffixes: tuple[str, ...]) -> None:
        for subtitle in subtitles:
            for line in self._extract_original_lines(subtitle.content):
                normalized = line.lower().strip().rstrip(".,!?;:")
                self.assertFalse(
                    any(normalized.endswith(suffix) for suffix in forbidden_suffixes),
                    msg=f"unexpected english break: {line}",
                )

    def test_normalize_segments_avoids_single_word_middle_fragment(self) -> None:
        segments = normalize_segments(
            [
                TranscriptSegment(
                    index=1,
                    start=0.0,
                    end=8.0,
                    text="and techniques that will allow you to serve an effective float serve.",
                )
            ]
        )

        self.assertGreater(len(segments), 1)
        self.assertNotIn("to", [segment.text for segment in segments])
        self.assertTrue(all(len(segment.text.split()) >= 2 for segment in segments))

    def test_normalize_segments_splits_long_source_before_translation(self) -> None:
        source_segment = TranscriptSegment(
            index=1,
            start=0.0,
            end=12.0,
            text=(
                "Today we're going to introduce five drills that you can do at home on your own wall "
                "so you can build better platform control and footwork timing."
            ),
        )

        normalized = normalize_segments([source_segment])

        self.assertGreater(len(normalized), 1)
        self.assertEqual(normalized[0].start, source_segment.start)
        self.assertEqual(normalized[-1].end, source_segment.end)
        self.assertEqual(" ".join(segment.text for segment in normalized), " ".join(source_segment.text.split()))
        self.assertTrue(all(segment.start < segment.end for segment in normalized))
        self.assertFalse(any(segment.text.lower().strip().endswith("on your") for segment in normalized))
        self.assertFalse(any(segment.text.lower().strip() == "five drills" for segment in normalized))

    def test_bilingual_subtitles_keep_one_cue_per_normalized_segment(self) -> None:
        segments = normalize_segments(
            [
                TranscriptSegment(
                    index=1,
                    start=0.0,
                    end=12.0,
                    text=(
                        "Step 1 keeps your platform still during contact. "
                        "Step 2 drives the ball with your legs through the target. "
                        "Step 3 holds the angle so the passer can control direction."
                    ),
                )
            ]
        )
        translations = [f"第{index}段译文说明：{segment.text}" for index, segment in enumerate(segments, start=1)]

        subtitles = build_bilingual_subtitles(segments, translations)

        self.assertEqual(len(subtitles), len(segments))
        for subtitle, segment in zip(subtitles, segments, strict=True):
            translation_text, original_text = self._split_bilingual_blocks(subtitle.content)
            self.assertEqual(subtitle.start.total_seconds(), segment.start)
            self.assertEqual(subtitle.end.total_seconds(), segment.end)
            self.assertTrue(translation_text)
            self.assertTrue(original_text)
            self.assertIn(segment.text, original_text)

    def test_bilingual_subtitles_wrap_inside_single_cue_without_new_time_slices(self) -> None:
        segment = TranscriptSegment(
            index=1,
            start=0.0,
            end=6.0,
            text="Short source line.",
        )

        subtitles = build_bilingual_subtitles(
            [segment],
            ["这是一条会在同一个 cue 内换成两行显示的较长译文内容，用来验证不会新增时间片。"],
        )

        self.assertEqual(len(subtitles), 1)
        self.assertEqual(subtitles[0].start.total_seconds(), segment.start)
        self.assertEqual(subtitles[0].end.total_seconds(), segment.end)
        self.assertGreaterEqual(len(subtitles[0].content.splitlines()), 2)

    def test_translation_subtitles_keep_one_cue_per_segment_even_when_text_wraps(self) -> None:
        segments = [
            TranscriptSegment(index=1, start=0.0, end=4.0, text="alpha"),
            TranscriptSegment(index=2, start=4.0, end=8.0, text="beta"),
        ]
        translations = [
            "这是一条会在同一个 cue 内换行显示的较长译文内容，用来验证 translation builder 不再二次切时间片。",
            "第二条译文保持独立。",
        ]

        subtitles = build_translation_subtitles(segments, translations)

        self.assertEqual(len(subtitles), len(segments))
        for subtitle, segment in zip(subtitles, segments, strict=True):
            self.assertEqual(subtitle.start.total_seconds(), segment.start)
            self.assertEqual(subtitle.end.total_seconds(), segment.end)

    def test_bilingual_output_keeps_upstream_split_points_readable(self) -> None:
        source_segment = TranscriptSegment(
            index=1,
            start=0.0,
            end=12.0,
            text=(
                "Today we're going to introduce five drills that you can do at home on your own wall "
                "so you can build better platform control and footwork timing."
            ),
        )
        segments = normalize_segments([source_segment])
        translations = [f"第{index}段译文：为了练习平台控制和脚步节奏。" for index, _ in enumerate(segments, start=1)]

        subtitles = build_bilingual_subtitles(segments, translations)

        self.assertEqual(len(subtitles), len(segments))
        self._assert_no_bad_english_breaks(subtitles, ("going to introduce", "on your", "with a", "how to"))

    def test_translation_prompt_calls_for_preserving_urls_and_names(self) -> None:
        messages = build_translation_messages(
            "volleyball tutorial",
            [TranscriptSegment(index=1, start=0.0, end=1.0, text="Coach Donny posted this on elevateyourself.org")],
        )

        self.assertIn("URL", messages[1]["content"])
        self.assertIn("专有名词", messages[1]["content"])
        self.assertIn("人物称呼", messages[1]["content"])
        self.assertIn("排球", messages[1]["content"])
        self.assertIn("passing", messages[1]["content"])
        self.assertIn("float serve", messages[1]["content"])


class SubtitleSegmentationPolicyTests(unittest.TestCase):
    def test_keeps_low_rate_segment_unsplit(self) -> None:
        segment = TranscriptSegment(
            index=1,
            start=0.0,
            end=4.0,
            text="Keep your platform quiet and hold the finish.",
        )

        normalized = normalize_segments([segment])

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].text, segment.text)

    def test_splits_high_rate_segment_at_word_timestamp_pause(self) -> None:
        words = (
            TranscriptWord(start=0.0, end=0.2, text="The"),
            TranscriptWord(start=0.2, end=0.4, text="quick"),
            TranscriptWord(start=0.4, end=0.6, text="brown"),
            TranscriptWord(start=0.6, end=0.85, text="fox"),
            TranscriptWord(start=1.7, end=1.9, text="jumps"),
            TranscriptWord(start=1.9, end=2.05, text="over"),
            TranscriptWord(start=2.05, end=2.2, text="the"),
            TranscriptWord(start=2.2, end=2.35, text="lazy"),
            TranscriptWord(start=2.35, end=2.5, text="dog"),
            TranscriptWord(start=2.5, end=2.65, text="near"),
            TranscriptWord(start=2.65, end=2.8, text="the"),
            TranscriptWord(start=2.8, end=3.0, text="fence"),
        )
        segment = TranscriptSegment(
            index=1,
            start=0.0,
            end=3.0,
            text="The quick brown fox jumps over the lazy dog near the fence",
            words=words,
        )

        normalized = normalize_segments([segment])

        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0].text, "The quick brown fox")
        self.assertEqual(normalized[1].text, "jumps over the lazy dog near the fence")
        # 断点使用词时间戳：第一块结束在 "fox" 的真实 end，而不是长度加权值。
        self.assertEqual(normalized[0].end, 0.85)
        self.assertEqual(normalized[1].start, 0.85)

    def test_high_rate_segment_falls_back_to_weighted_times_without_words(self) -> None:
        segment = TranscriptSegment(
            index=1,
            start=0.0,
            end=3.0,
            text="The quick brown fox jumps over the lazy dog near the fence",
        )

        normalized = normalize_segments([segment])

        self.assertEqual(len(normalized), 2)
        self.assertEqual(
            " ".join(segment.text for segment in normalized),
            " ".join(segment.text.split()),
        )
        self.assertEqual(normalized[0].start, 0.0)
        self.assertEqual(normalized[-1].end, 3.0)

    def test_splits_segment_exceeding_max_duration(self) -> None:
        segment = TranscriptSegment(
            index=1,
            start=0.0,
            end=7.0,
            text="Short sentence held for a very long time.",
        )

        normalized = normalize_segments([segment])

        self.assertGreater(len(normalized), 1)
        self.assertEqual(normalized[0].start, 0.0)
        self.assertEqual(normalized[-1].end, 7.0)

    def test_settings_override_affects_split_decision(self) -> None:
        segment = TranscriptSegment(
            index=1,
            start=0.0,
            end=6.0,
            text="A moderately long sentence without any rush at all my friend",
        )

        self.assertEqual(len(normalize_segments([segment])), 1)
        strict = normalize_segments([segment], settings=SubtitleSettings(max_cps=5.0))
        self.assertGreater(len(strict), 1)

    def test_merges_short_segments_into_previous_neighbor(self) -> None:
        segments = [
            TranscriptSegment(index=1, start=0.0, end=3.0, text="First complete sentence."),
            TranscriptSegment(index=2, start=3.1, end=3.4, text="Okay."),
            TranscriptSegment(index=3, start=3.5, end=6.0, text="Then the next part."),
        ]

        normalized = normalize_segments(segments, settings=SubtitleSettings(gap_close=False))

        self.assertEqual(len(normalized), 2)
        self.assertIn("Okay", normalized[0].text)
        self.assertEqual(normalized[0].start, 0.0)
        self.assertEqual(normalized[0].end, 3.4)

    def test_merges_all_short_segments_into_single_fallback(self) -> None:
        segments = [
            TranscriptSegment(index=1, start=0.0, end=0.4, text="Go."),
            TranscriptSegment(index=2, start=0.5, end=0.9, text="Now."),
        ]

        normalized = normalize_segments(segments)

        self.assertEqual(len(normalized), 1)
        self.assertIn("Go", normalized[0].text)
        self.assertIn("Now", normalized[0].text)

    def test_merges_short_cjk_segment(self) -> None:
        segments = [
            TranscriptSegment(index=1, start=0.0, end=4.0, text="这是较长的完整句子内容。"),
            TranscriptSegment(index=2, start=4.1, end=4.4, text="是的"),
        ]

        normalized = normalize_segments(segments)

        self.assertEqual(len(normalized), 1)
        self.assertIn("是的", normalized[0].text)

    def test_enforces_max_duration_on_imbalanced_text_blocks(self) -> None:
        segment = TranscriptSegment(
            index=1,
            start=0.0,
            end=17.3,
            text=(
                "what a cool drill it was drill thanker. "
                "Guys your job is not to catch it because they are now"
            ),
        )

        normalized = normalize_segments([segment])

        self.assertGreater(len(normalized), 1)
        self.assertTrue(all(segment.end - segment.start <= 6.0 + 0.1 for segment in normalized))

    def test_word_timestamp_split_drops_fragment_breaks_to_weighted_fallback(self) -> None:
        words = (
            TranscriptWord(start=0.0, end=0.3, text="PABB"),
            TranscriptWord(start=1.2, end=1.4, text="coaching"),
            TranscriptWord(start=1.4, end=1.55, text="certification"),
            TranscriptWord(start=1.55, end=1.7, text="course"),
            TranscriptWord(start=1.7, end=1.8, text="expands"),
        )
        segment = TranscriptSegment(
            index=1,
            start=0.0,
            end=2.0,
            text="PABB coaching certification course expands",
            words=words,
        )

        normalized = normalize_segments([segment])

        # 词时间戳断点会把 4 字符的 "PABB" 切出来；碎片校验应放弃该路径，
        # 由带短块合并的加权 fallback 产出无碎片结果（可能因最短时长合并回单条）。
        self.assertFalse(any(segment.text == "PABB" for segment in normalized))
        self.assertTrue(all(len(segment.text.split()) >= 2 for segment in normalized))

    def test_closes_small_gaps_between_subtitles(self) -> None:
        segments = [
            TranscriptSegment(index=1, start=0.0, end=2.0, text="First line."),
            TranscriptSegment(index=2, start=2.2, end=4.0, text="Second line."),
        ]

        normalized = normalize_segments(segments)

        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0].end, round(2.2 - 2 / 24, 3))
        self.assertEqual(normalized[1].start, 2.2)

    def test_keeps_large_gaps_between_subtitles(self) -> None:
        segments = [
            TranscriptSegment(index=1, start=0.0, end=2.0, text="First complete line."),
            TranscriptSegment(index=2, start=2.8, end=4.5, text="Second complete line."),
        ]

        normalized = normalize_segments(segments)

        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0].end, 2.0)


if __name__ == "__main__":
    unittest.main()
