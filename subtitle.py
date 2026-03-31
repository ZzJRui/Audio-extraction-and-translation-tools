import math
from datetime import timedelta
from pathlib import Path
from typing import Iterable

import srt

from transcribe import TranscriptSegment
from text_safety import sanitize_utf8_text

CJK_LINE_LIMIT = 18
LATIN_LINE_LIMIT = 42
MAX_CJK_SEGMENT_LENGTH = 16
MAX_LATIN_SEGMENT_LENGTH = 36
MAX_SEGMENT_SPLITS = 3
MAX_BILINGUAL_SPLITS = 4
MAX_BILINGUAL_LINES = 3
SEGMENT_SEARCH_RADIUS = 12
MIN_SEGMENT_DURATION = 2.4
STRONG_BREAK_CHARS = "\u3002\uff01\uff1f?!"
WEAK_BREAK_CHARS = "\uff0c\uff1b\u3001,:;"
TERMINAL_PUNCTUATION = STRONG_BREAK_CHARS
MIN_CJK_CHUNK_LENGTH = 6
MIN_LATIN_CHUNK_WORDS = 2
MIN_LATIN_CHUNK_LENGTH = 8


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


def _join_pieces(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if _contains_cjk(left) or _contains_cjk(right):
        return f"{left}{right}"
    return " ".join([left, right]).strip()


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


def _find_balanced_split_index(text: str) -> int | None:
    target = max(1, len(text) // 2)
    search_radius = max(4, len(text) // 4)
    for break_chars in (STRONG_BREAK_CHARS + WEAK_BREAK_CHARS, " "):
        break_index = _find_best_break_index(
            text,
            target,
            break_chars,
            search_radius=search_radius,
        )
        if break_index is not None:
            return break_index
    return _find_safe_split_index(text, target)


def _strip_orphan_terminal_punctuation(first: str, second: str, original: str) -> tuple[str, str]:
    if len(second) == 1 and second in TERMINAL_PUNCTUATION and original.endswith(second):
        return first.rstrip(), ""
    return first, second


def _is_too_short_piece(text: str) -> bool:
    cleaned = _normalize_whitespace(text)
    if not cleaned:
        return True
    if _contains_cjk(cleaned):
        return len(cleaned) < MIN_CJK_CHUNK_LENGTH
    return len(cleaned.split()) < MIN_LATIN_CHUNK_WORDS or len(cleaned) < MIN_LATIN_CHUNK_LENGTH


def _merge_short_pieces(pieces: list[str]) -> list[str]:
    merged = [piece for piece in pieces if piece]
    changed = True
    while changed and len(merged) > 1:
        changed = False
        for index, piece in enumerate(list(merged)):
            if not _is_too_short_piece(piece):
                continue
            if index == 0:
                merged[1] = _join_pieces(merged[0], merged[1])
                del merged[0]
            elif index == len(merged) - 1:
                merged[-2] = _join_pieces(merged[-2], merged[-1])
                del merged[-1]
            else:
                merged[index + 1] = _join_pieces(merged[index], merged[index + 1])
                del merged[index]
            changed = True
            break
    return merged


def _split_text_to_chunks(
    text: str,
    max_length: int,
    *,
    max_pieces: int,
    desired_count: int | None = None,
) -> list[str]:
    cleaned = sanitize_utf8_text(_normalize_whitespace(text))
    if not cleaned:
        return []

    pieces = [cleaned]
    target_count = max(desired_count or 1, 1)

    while len(pieces) < target_count and len(pieces) < max_pieces:
        previous_pieces = list(pieces)
        piece_index = max(range(len(pieces)), key=lambda idx: len(pieces[idx]))
        split_index = _find_balanced_split_index(pieces[piece_index])
        if split_index is None:
            break
        left, right = _split_at_index(pieces[piece_index], split_index)
        if not left or not right:
            break
        pieces[piece_index : piece_index + 1] = [left, right]
        pieces = _merge_short_pieces(pieces)
        if pieces == previous_pieces:
            break

    while len(pieces) < max_pieces:
        oversized_indexes = [index for index, piece in enumerate(pieces) if len(piece) > max_length]
        if not oversized_indexes:
            break
        previous_pieces = list(pieces)
        piece_index = max(oversized_indexes, key=lambda idx: len(pieces[idx]))
        piece = pieces[piece_index]
        split_index = None
        for break_chars in (STRONG_BREAK_CHARS, WEAK_BREAK_CHARS, " "):
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
        left, right = _strip_orphan_terminal_punctuation(left, right, piece)
        if left and not right:
            pieces[piece_index : piece_index + 1] = [left]
            break
        if not left or not right:
            break
        pieces[piece_index : piece_index + 1] = [left, right]
        pieces = _merge_short_pieces(pieces)
        if pieces == previous_pieces:
            break

    return [piece for piece in pieces if piece]


def _split_two_lines(text: str, limit: int) -> tuple[str, str]:
    pieces = _split_text_to_chunks(text, limit, max_pieces=2)
    if len(pieces) == 1:
        return pieces[0], ""
    return pieces[0], pieces[1]


def _format_text_block(text: str, limit: int) -> str:
    cleaned = sanitize_utf8_text(_normalize_whitespace(text))
    if not cleaned or len(cleaned) <= limit:
        return cleaned

    first, second = _split_two_lines(cleaned, limit)
    if not second:
        return first
    return f"{first}\n{second}"


def _join_piece_group(pieces: list[str]) -> str:
    if not pieces:
        return ""

    joined = pieces[0]
    for piece in pieces[1:]:
        joined = _join_pieces(joined, piece)
    return joined


def _split_text_to_lines(text: str, limit: int) -> list[str]:
    cleaned = sanitize_utf8_text(_normalize_whitespace(text))
    if not cleaned:
        return []

    estimated_lines = max(1, math.ceil(len(cleaned) / max(limit, 1)) + 2)
    return _split_text_to_chunks(cleaned, limit, max_pieces=estimated_lines)


def _take_prefix_lines(text: str, limit: int, max_lines: int) -> tuple[list[str], list[str]]:
    if max_lines <= 0:
        return [], _split_text_to_lines(text, limit)

    lines = _split_text_to_lines(text, limit)
    if len(lines) <= max_lines:
        return lines, []

    prefix = lines[:max_lines]
    rest = lines[max_lines:]

    while rest and _is_too_short_piece(_join_piece_group(rest)) and len(prefix) > 1:
        rest = [prefix.pop()] + rest

    return prefix, rest


def _compose_bilingual_content(translation_text: str, original_text: str) -> str:
    blocks = [block for block in (translation_text, original_text) if block]
    return "\n".join(blocks)


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


def _split_bilingual_pair(segment: TranscriptSegment, translation: str) -> list[tuple[float, float, str, str]]:
    original_text = sanitize_utf8_text(_normalize_whitespace(segment.text))
    translation_text = sanitize_utf8_text(_normalize_whitespace(translation))
    original_limit = _display_limit(original_text)
    translation_limit = _display_limit(translation_text)

    bilingual_pieces: list[tuple[str, str]] = []
    remaining_original = original_text
    remaining_translation = translation_text

    while remaining_original or remaining_translation:
        original_lines = _split_text_to_lines(remaining_original, original_limit)
        translation_lines = _split_text_to_lines(remaining_translation, translation_limit)

        if len(original_lines) + len(translation_lines) <= MAX_BILINGUAL_LINES:
            bilingual_pieces.append(("\n".join(translation_lines), "\n".join(original_lines)))
            break

        if not remaining_original:
            translation_budget = MAX_BILINGUAL_LINES
            original_budget = 0
        elif not remaining_translation:
            translation_budget = 0
            original_budget = MAX_BILINGUAL_LINES
        elif len(translation_lines) <= 1:
            translation_budget = 1
            original_budget = MAX_BILINGUAL_LINES - 1
        elif len(original_lines) <= 1:
            translation_budget = MAX_BILINGUAL_LINES - 1
            original_budget = 1
        elif len(translation_lines) > len(original_lines):
            translation_budget = 2
            original_budget = 1
        elif len(original_lines) > len(translation_lines):
            translation_budget = 1
            original_budget = 2
        elif len(remaining_translation) >= len(remaining_original):
            translation_budget = 2
            original_budget = 1
        else:
            translation_budget = 1
            original_budget = 2

        translation_prefix, translation_rest = _take_prefix_lines(
            remaining_translation,
            translation_limit,
            translation_budget,
        )
        original_prefix, original_rest = _take_prefix_lines(
            remaining_original,
            original_limit,
            original_budget,
        )

        translation_block = "\n".join(translation_prefix)
        original_block = "\n".join(original_prefix)
        if not translation_block and not original_block:
            break

        bilingual_pieces.append((translation_block, original_block))
        remaining_translation = _join_piece_group(translation_rest)
        remaining_original = _join_piece_group(original_rest)

    weights = [max(len(translation_piece) + len(original_piece), 1) for translation_piece, original_piece in bilingual_pieces]
    total_weight = sum(weights)
    duration = max(segment.end - segment.start, 0.0)

    results: list[tuple[float, float, str, str]] = []
    current_start = segment.start
    for index, (translation_piece, original_piece) in enumerate(bilingual_pieces):
        if index == len(bilingual_pieces) - 1:
            current_end = segment.end
        else:
            current_end = current_start + (duration * weights[index] / total_weight)
        results.append((current_start, current_end, translation_piece, original_piece))
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
            _distribute_segment_times(
                cleaned_segment,
                _split_text_to_chunks(cleaned_text, max_length, max_pieces=MAX_SEGMENT_SPLITS),
            )
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
    subtitles: list[srt.Subtitle] = []
    subtitle_index = 1

    for segment, translation in zip(segments, translations, strict=True):
        for start, end, translation_piece, original_piece in _split_bilingual_pair(segment, translation):
            subtitles.append(
                srt.Subtitle(
                    index=subtitle_index,
                    start=_timedelta(start),
                    end=_timedelta(end),
                    content=_compose_bilingual_content(translation_piece, original_piece),
                )
            )
            subtitle_index += 1

    return subtitles


def write_srt_file(path: str | Path, subtitles: Iterable[srt.Subtitle]) -> None:
    content = srt.compose(list(subtitles))
    safe_content = sanitize_utf8_text(content)
    Path(path).write_text(safe_content, encoding="utf-8")
