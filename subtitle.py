from datetime import timedelta
from pathlib import Path
from typing import Iterable

import srt

from transcribe import TranscriptSegment


def _timedelta(seconds: float):
    return timedelta(seconds=max(seconds, 0.0))


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split()) if not _contains_cjk(text) else text.strip()


def _find_break_position(text: str, limit: int, break_chars: str) -> int | None:
    if len(text) <= limit:
        return None

    search_end = min(limit, len(text) - 1)
    for index in range(search_end, max(0, search_end - 10), -1):
        if text[index] in break_chars:
            return index
    return None


def _split_two_lines(text: str, limit: int, break_chars: str, break_on_space: bool) -> tuple[str, str]:
    break_index = _find_break_position(text, limit, break_chars)
    if break_index is None:
        break_index = min(limit, len(text) - 1)

    if break_on_space and text[break_index].isspace():
        first = text[:break_index].strip()
        second = text[break_index + 1 :].strip()
    else:
        first = text[: break_index + 1].strip()
        second = text[break_index + 1 :].strip()

    if not first:
        first = text[:limit].strip()
        second = text[limit:].strip()

    return first, second


def _format_text_block(text: str, limit: int, break_chars: str, break_on_space: bool) -> str:
    cleaned = _normalize_whitespace(text)
    if not cleaned or len(cleaned) <= limit:
        return cleaned

    first, second = _split_two_lines(cleaned, limit, break_chars, break_on_space)
    if not second:
        return first
    return f"{first}\n{second}"


def format_original_text(text: str) -> str:
    if _contains_cjk(text):
        return _format_text_block(text, limit=18, break_chars="，。！？；：、", break_on_space=False)
    return _format_text_block(text, limit=42, break_chars=",.!?;: ", break_on_space=True)


def format_translation_text(text: str) -> str:
    return _format_text_block(text, limit=18, break_chars="，。！？；：、", break_on_space=False)


def build_original_subtitles(segments: list[TranscriptSegment]) -> list[srt.Subtitle]:
    return [
        srt.Subtitle(
            index=segment.index,
            start=_timedelta(segment.start),
            end=_timedelta(segment.end),
            content=format_original_text(segment.text),
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
            content=format_translation_text(translation),
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
            content=f"{format_translation_text(translation)}\n{format_original_text(segment.text)}",
        )
        for segment, translation in zip(segments, translations, strict=True)
    ]


def write_srt_file(path: str | Path, subtitles: Iterable[srt.Subtitle]) -> None:
    Path(path).write_text(srt.compose(list(subtitles)), encoding="utf-8")
