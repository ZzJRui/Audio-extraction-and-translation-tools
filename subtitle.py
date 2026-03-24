from datetime import timedelta
from pathlib import Path
from typing import Iterable

import srt

from transcribe import TranscriptSegment

CJK_LINE_LIMIT = 18
LATIN_LINE_LIMIT = 42
MAX_CJK_SEGMENT_LENGTH = 16
MAX_LATIN_SEGMENT_LENGTH = 36
MAX_SEGMENT_SPLITS = 3
SEGMENT_SEARCH_RADIUS = 12
MIN_SEGMENT_DURATION = 2.4
STRONG_BREAK_CHARS = "。！？.!?"
WEAK_BREAK_CHARS = "，；：,;:"
TERMINAL_PUNCTUATION = "。！？.!?"


def _timedelta(seconds: float):
    return timedelta(seconds=max(seconds, 0.0))


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split()) if not _contains_cjk(text) else text.strip()


def _display_limit(text: str) -> int:
    return CJK_LINE_LIMIT if _contains_cjk(text) else LATIN_LINE_LIMIT


def _segment_length_limit(text: str) -> int:
    return MAX_CJK_SEGMENT_LENGTH if _contains_cjk(text) else MAX_LATIN_SEGMENT_LENGTH


def _split_at_index(text: str, break_index: int) -> tuple[str, str]:
    if text[break_index].isspace():
        left = text[:break_index].strip()
        right = text[break_index + 1 :].strip()
    else:
        left = text[: break_index + 1].strip()
        right = text[break_index + 1 :].strip()
    return left, right


def _score_break_index(index: int, target: int) -> tuple[int, int]:
    return (abs(index - target), 0 if index <= target else 1)


def _find_best_break_index(
    text: str,
    target: int,
    break_chars: str,
    *,
    search_radius: int,
) -> int | None:
    if len(text) <= target:
        return None

    search_start = max(1, target - search_radius)
    search_end = min(len(text) - 2, target + search_radius)
    candidates: list[tuple[tuple[int, int], int]] = []

    for index in range(search_start, search_end + 1):
        if text[index] not in break_chars:
            continue
        left, right = _split_at_index(text, index)
        if not left or not right:
            continue
        candidates.append((_score_break_index(index, target), index))

    if not candidates:
        return None

    return min(candidates, key=lambda item: item[0])[1]


def _find_safe_split_index(text: str, target: int) -> int | None:
    if len(text) <= target:
        return None

    if not _contains_cjk(text):
        index = _find_best_break_index(
            text,
            target,
            " ",
            search_radius=SEGMENT_SEARCH_RADIUS * 2,
        )
        if index is not None:
            return index

    fallback_index = min(target, len(text) - 2)
    left, right = _split_at_index(text, fallback_index)
    if not left or not right:
        return None
    return fallback_index


def _strip_orphan_terminal_punctuation(first: str, second: str, original: str) -> tuple[str, str]:
    if len(second) == 1 and second in TERMINAL_PUNCTUATION and original.endswith(second):
        return first.rstrip(), ""
    return first, second


def _split_two_lines(text: str, limit: int) -> tuple[str, str]:
    for break_chars in (STRONG_BREAK_CHARS + WEAK_BREAK_CHARS, " "):
        break_index = _find_best_break_index(
            text,
            limit,
            break_chars,
            search_radius=8 if break_chars != " " else 12,
        )
        if break_index is not None:
            first, second = _split_at_index(text, break_index)
            return _strip_orphan_terminal_punctuation(first, second, text)

    break_index = min(limit, len(text) - 2)
    first, second = _split_at_index(text, break_index)
    return _strip_orphan_terminal_punctuation(first, second, text)


def _format_text_block(text: str, limit: int) -> str:
    cleaned = _normalize_whitespace(text)
    if not cleaned or len(cleaned) <= limit:
        return cleaned

    first, second = _split_two_lines(cleaned, limit)
    if not second:
        return first
    return f"{first}\n{second}"


def _split_segment_text(text: str, max_length: int) -> list[str]:
    pieces = [text]
    while len(pieces) < MAX_SEGMENT_SPLITS:
        oversized_indexes = [index for index, piece in enumerate(pieces) if len(piece) > max_length]
        if not oversized_indexes:
            break

        piece_index = max(oversized_indexes, key=lambda index: len(pieces[index]))
        piece = pieces[piece_index]
        split_index = None
        for break_chars in (STRONG_BREAK_CHARS, WEAK_BREAK_CHARS):
            split_index = _find_best_break_index(
                piece,
                max_length,
                break_chars,
                search_radius=SEGMENT_SEARCH_RADIUS,
            )
            if split_index is not None:
                break

        if split_index is None:
            split_index = _find_safe_split_index(piece, max_length)
        if split_index is None:
            break

        left, right = _split_at_index(piece, split_index)
        if not left or not right:
            break

        pieces[piece_index : piece_index + 1] = [left, right]

    return pieces


def _distribute_segment_times(segment: TranscriptSegment, pieces: list[str]) -> list[TranscriptSegment]:
    if len(pieces) == 1:
        return [
            TranscriptSegment(
                index=segment.index,
                start=segment.start,
                end=segment.end,
                text=pieces[0],
            )
        ]

    weights = [max(len(piece), 1) for piece in pieces]
    total_weight = sum(weights)
    duration = max(segment.end - segment.start, 0.0)

    results: list[TranscriptSegment] = []
    current_start = segment.start
    for piece_index, piece in enumerate(pieces):
        if piece_index == len(pieces) - 1:
            current_end = segment.end
        else:
            current_end = current_start + (duration * weights[piece_index] / total_weight)
        results.append(
            TranscriptSegment(
                index=segment.index + piece_index,
                start=current_start,
                end=current_end,
                text=piece,
            )
        )
        current_start = current_end

    return results


def normalize_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    normalized_segments: list[TranscriptSegment] = []

    for segment in segments:
        cleaned_text = _normalize_whitespace(segment.text)
        if not cleaned_text:
            continue

        cleaned_segment = TranscriptSegment(
            index=segment.index,
            start=segment.start,
            end=segment.end,
            text=cleaned_text,
        )
        max_length = _segment_length_limit(cleaned_text)
        should_split = len(cleaned_text) > max_length and (cleaned_segment.end - cleaned_segment.start) >= MIN_SEGMENT_DURATION

        split_segments = (
            _distribute_segment_times(cleaned_segment, _split_segment_text(cleaned_text, max_length))
            if should_split
            else [cleaned_segment]
        )
        normalized_segments.extend(split_segments)

    reindexed_segments: list[TranscriptSegment] = []
    for index, segment in enumerate(normalized_segments, start=1):
        reindexed_segments.append(
            TranscriptSegment(
                index=index,
                start=segment.start,
                end=segment.end,
                text=segment.text,
            )
        )

    return reindexed_segments


def format_original_text(text: str) -> str:
    return _format_text_block(text, limit=_display_limit(text))


def format_translation_text(text: str) -> str:
    return _format_text_block(text, limit=_display_limit(text))


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
