from datetime import timedelta
from pathlib import Path
from typing import Iterable

import srt

from transcribe import TranscriptSegment


def _timedelta(seconds: float):
    return timedelta(seconds=max(seconds, 0.0))


def build_original_subtitles(segments: list[TranscriptSegment]) -> list[srt.Subtitle]:
    return [
        srt.Subtitle(
            index=segment.index,
            start=_timedelta(segment.start),
            end=_timedelta(segment.end),
            content=segment.text,
        )
        for segment in segments
    ]


def build_translation_subtitles(
    segments: list[TranscriptSegment],
    translations: list[str],
) -> list[srt.Subtitle]:
    return [
        srt.Subtitle(
            index=segment.index,
            start=_timedelta(segment.start),
            end=_timedelta(segment.end),
            content=translation,
        )
        for segment, translation in zip(segments, translations, strict=True)
    ]


def build_bilingual_subtitles(
    segments: list[TranscriptSegment],
    translations: list[str],
) -> list[srt.Subtitle]:
    return [
        srt.Subtitle(
            index=segment.index,
            start=_timedelta(segment.start),
            end=_timedelta(segment.end),
            content=f"{translation}\n{segment.text}",
        )
        for segment, translation in zip(segments, translations, strict=True)
    ]


def write_srt_file(path: str | Path, subtitles: Iterable[srt.Subtitle]) -> None:
    Path(path).write_text(srt.compose(list(subtitles)), encoding="utf-8")
