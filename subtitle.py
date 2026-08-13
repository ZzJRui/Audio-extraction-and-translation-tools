import math
import string
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Iterable

import srt

from config import (
    DEFAULT_SUBTITLE_GAP_CLOSE,
    DEFAULT_SUBTITLE_MAX_CPS,
    DEFAULT_SUBTITLE_MAX_DURATION,
    DEFAULT_SUBTITLE_MIN_DURATION,
    DEFAULT_SUBTITLE_MIN_GAP,
)
from transcribe import TranscriptSegment
from text_safety import sanitize_utf8_text

CJK_LINE_LIMIT = 18
LATIN_LINE_LIMIT = 42
MAX_CJK_SEGMENT_LENGTH = 16
MAX_LATIN_CUE_CHARS = 84
MAX_SEGMENT_SPLITS = 4
SEGMENT_SEARCH_RADIUS = 12
MIN_SEGMENT_DURATION = 2.4
MIN_FRAME_GAP = 2 / 24.0  # Netflix: minimum 2 frames between subtitles at 24 fps
STRONG_BREAK_CHARS = "\u3002\uff01\uff1f?!."
WEAK_BREAK_CHARS = "\uff0c\uff1b\u3001,:;"
TERMINAL_PUNCTUATION = STRONG_BREAK_CHARS
MIN_CJK_CHUNK_LENGTH = 6
MIN_LATIN_CHUNK_WORDS = 2
MIN_LATIN_CHUNK_LENGTH = 8


@dataclass(frozen=True)
class SubtitleSettings:
    max_cps: float = DEFAULT_SUBTITLE_MAX_CPS
    min_duration: float = DEFAULT_SUBTITLE_MIN_DURATION
    max_duration: float = DEFAULT_SUBTITLE_MAX_DURATION
    min_gap: float = DEFAULT_SUBTITLE_MIN_GAP
    gap_close: bool = DEFAULT_SUBTITLE_GAP_CLOSE


DEFAULT_SUBTITLE_SETTINGS = SubtitleSettings()


ENGLISH_BAD_END_TOKENS = {
    "a",
    "an",
    "and",
    "at",
    "because",
    "but",
    "by",
    "for",
    "from",
    "if",
    "in",
    "into",
    "of",
    "on",
    "or",
    "so",
    "the",
    "through",
    "to",
    "with",
}
ENGLISH_BAD_END_PHRASES = {
    ("and", "how"),
    ("how", "to"),
    ("on", "my"),
    ("on", "our"),
    ("on", "the"),
    ("on", "your"),
    ("time", "to"),
    ("trying", "to"),
    ("want", "to"),
    ("with", "a"),
    ("with", "the"),
}
ENGLISH_BAD_END_TRIGRAMS = {
    ("going", "to", "introduce"),
    ("need", "to", "be"),
    ("want", "to", "be"),
}
ENGLISH_GOOD_START_TOKENS = {
    "after",
    "and",
    "because",
    "before",
    "but",
    "if",
    "so",
    "that",
    "then",
    "when",
    "while",
}
ENGLISH_GOOD_START_PHRASES = {
    ("and", "how"),
    ("so", "you"),
    ("that", "you"),
}


def _round_seconds(seconds: float) -> float:
    return round(max(seconds, 0.0) + 1e-9, 3)


def _timedelta(seconds: float):
    return timedelta(seconds=_round_seconds(seconds))


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _contains_latin(text: str) -> bool:
    return any(("A" <= char <= "Z") or ("a" <= char <= "z") for char in text)


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split()) if not _contains_cjk(text) else text.strip()


def _display_limit(text: str) -> int:
    return CJK_LINE_LIMIT if _contains_cjk(text) else LATIN_LINE_LIMIT


def _cue_length_limit(text: str) -> int:
    return MAX_CJK_SEGMENT_LENGTH if _contains_cjk(text) else MAX_LATIN_CUE_CHARS


def _should_split_segment(segment: TranscriptSegment, settings: SubtitleSettings) -> bool:
    duration = segment.end - segment.start
    text_len = len(segment.text)
    if text_len == 0:
        return False

    if _contains_cjk(segment.text):
        if text_len > MAX_CJK_SEGMENT_LENGTH and duration >= MIN_SEGMENT_DURATION:
            return True
        return settings.max_duration > 0 and duration > settings.max_duration

    if text_len > MAX_LATIN_CUE_CHARS:
        return True
    if settings.max_duration > 0 and duration > settings.max_duration:
        return True
    if duration > 0 and settings.max_cps > 0 and text_len / duration > settings.max_cps:
        return True
    return False


def _target_piece_count(segment: TranscriptSegment, settings: SubtitleSettings) -> int:
    duration = max(segment.end - segment.start, 0.0)
    text_len = len(segment.text)
    is_cjk = _contains_cjk(segment.text)
    max_length = MAX_CJK_SEGMENT_LENGTH if is_cjk else MAX_LATIN_CUE_CHARS

    count = max(1, math.ceil(text_len / max_length))
    if settings.max_duration > 0 and duration > settings.max_duration:
        count = max(count, math.ceil(duration / settings.max_duration))
    if not is_cjk and duration > 0 and settings.max_cps > 0:
        avg_cps = text_len / duration
        if avg_cps > settings.max_cps:
            count = max(count, math.ceil(text_len / (settings.max_cps * duration)))
    # 上限与时长联动：6 秒规则需要的块数不能被固定上限截断
    cap = MAX_SEGMENT_SPLITS
    if settings.max_duration > 0:
        cap = max(MAX_SEGMENT_SPLITS, math.ceil(duration / settings.max_duration))
    return min(count, cap)


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


def _normalize_latin_token(token: str) -> str:
    return token.strip(string.whitespace + string.punctuation + '"\'`“”‘’').lower()


def _latin_tokens(text: str) -> list[str]:
    return [token for token in (_normalize_latin_token(piece) for piece in text.split()) if token]


def _score_break_index(text: str, index: int, target: int) -> tuple[int, int, int]:
    penalty = 0
    if not _contains_cjk(text):
        left, right = _split_at_index(text, index)
        left_tokens = _latin_tokens(left)
        right_tokens = _latin_tokens(right)

        if len(left_tokens) < MIN_LATIN_CHUNK_WORDS or len(right_tokens) < MIN_LATIN_CHUNK_WORDS:
            penalty += 20

        if left_tokens:
            if left_tokens[-1] in ENGLISH_BAD_END_TOKENS:
                penalty += 18
            if tuple(left_tokens[-2:]) in ENGLISH_BAD_END_PHRASES:
                penalty += 32
            if tuple(left_tokens[-3:]) in ENGLISH_BAD_END_TRIGRAMS:
                penalty += 40

        if right_tokens:
            if right_tokens[0] in ENGLISH_GOOD_START_TOKENS:
                penalty -= 6
            if tuple(right_tokens[:2]) in ENGLISH_GOOD_START_PHRASES:
                penalty -= 10

        if text[index] in STRONG_BREAK_CHARS:
            penalty -= 12
        elif text[index] in WEAK_BREAK_CHARS:
            penalty -= 6

    return (penalty, abs(index - target), 0 if index <= target else 1)


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
    candidates: list[tuple[tuple[int, int, int], int]] = []

    for index in range(search_start, search_end + 1):
        if text[index] not in break_chars:
            continue
        left, right = _split_at_index(text, index)
        if not left or not right:
            continue
        candidates.append((_score_break_index(text, index, target), index))

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


def _is_short_segment(segment: TranscriptSegment, min_duration: float) -> bool:
    text = _normalize_whitespace(segment.text)
    if not text:
        return True
    duration = segment.end - segment.start
    if duration < min_duration:
        return True
    # 1-2 词的短句只有时长也明显偏短时才视为碎片（避免误并读得完的短句）
    if _contains_cjk(text):
        return len(text) <= 2 and duration < 2 * min_duration
    return len(text.split()) <= 2 and duration < 2 * min_duration


def _merge_short_segments(
    segments: list[TranscriptSegment],
    min_duration: float,
) -> list[TranscriptSegment]:
    """Merge raw segments that are too short into a neighbor (borrowing time).

    A segment is considered too short when its duration is below min_duration or
    its text has at most two words. Short segments are buffered and attached to
    the previously emitted segment when the next regular segment arrives; any
    trailing buffer is appended to the last emitted segment. Timestamps use the
    union of the merged ranges.
    """
    merged: list[TranscriptSegment] = []
    pending_parts: list[str] = []
    pending_start: float | None = None
    pending_end: float | None = None

    def attach(segment: TranscriptSegment, parts: list[str], start: float | None, end: float | None) -> TranscriptSegment:
        combined = segment.text
        for part in parts:
            combined = _join_pieces(combined, part)
        new_start = min(start, segment.start) if start is not None else segment.start
        new_end = max(end, segment.end) if end is not None else segment.end
        return TranscriptSegment(
            index=segment.index,
            start=_round_seconds(new_start),
            end=_round_seconds(new_end),
            text=combined,
        )

    for segment in segments:
        text = _normalize_whitespace(segment.text)
        if not text:
            continue
        cleaned = TranscriptSegment(
            index=segment.index,
            start=_round_seconds(segment.start),
            end=_round_seconds(segment.end),
            text=text,
            words=segment.words,
        )
        if _is_short_segment(cleaned, min_duration):
            pending_parts.append(cleaned.text)
            pending_start = cleaned.start if pending_start is None else min(pending_start, cleaned.start)
            pending_end = cleaned.end if pending_end is None else max(pending_end, cleaned.end)
            continue

        if pending_parts and merged:
            last = merged[-1]
            merged[-1] = attach(last, pending_parts, pending_start, pending_end)
            pending_parts = []
            pending_start = None
            pending_end = None
        elif pending_parts:
            cleaned = attach(cleaned, pending_parts, pending_start, pending_end)
            pending_parts = []
            pending_start = None
            pending_end = None

        merged.append(cleaned)

    if pending_parts:
        if merged:
            last = merged[-1]
            merged[-1] = attach(last, pending_parts, pending_start, pending_end)
        else:
            combined = ""
            for part in pending_parts:
                combined = _join_pieces(combined, part)
            merged.append(
                TranscriptSegment(
                    index=1,
                    start=_round_seconds(pending_start or 0.0),
                    end=_round_seconds(pending_end or (pending_start or 0.0)),
                    text=combined,
                )
            )

    return merged


def _close_gaps(
    segments: list[TranscriptSegment],
    min_gap: float,
) -> list[TranscriptSegment]:
    """Close small gaps between consecutive subtitles (Netflix chaining).

    Gaps smaller than min_gap are closed by extending the previous subtitle's
    out-time to two frames before the next subtitle's in-time. Gaps of at least
    min_gap are preserved. First/last boundaries are left untouched.
    """
    if min_gap <= 0:
        return list(segments)

    result = list(segments)
    for index in range(len(result) - 1):
        previous = result[index]
        current = result[index + 1]
        gap = current.start - previous.end
        if not (0 < gap < min_gap):
            continue
        new_end = _round_seconds(current.start - MIN_FRAME_GAP)
        if new_end <= previous.start:
            continue
        result[index] = TranscriptSegment(
            index=previous.index,
            start=previous.start,
            end=new_end,
            text=previous.text,
        )
    return result


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


def _split_text_to_lines(text: str, limit: int) -> list[str]:
    cleaned = sanitize_utf8_text(_normalize_whitespace(text))
    if not cleaned:
        return []

    estimated_lines = max(1, math.ceil(len(cleaned) / max(limit, 1)))
    return _split_text_to_chunks(cleaned, limit, max_pieces=estimated_lines)


def _compose_bilingual_content(translation_text: str, original_text: str) -> str:
    blocks = [block for block in (translation_text, original_text) if block]
    return "\n".join(blocks)


def _compose_single_mode_content(text: str) -> str:
    return "\n".join(_split_text_to_lines(text, _display_limit(text)))


def _find_nearest_break_index(text: str, char_pos: int) -> int | None:
    if len(text) < 2:
        return None
    radius = max(4, min(SEGMENT_SEARCH_RADIUS * 2, len(text) // 2))
    search_start = max(1, char_pos - radius)
    search_end = min(len(text) - 1, char_pos + radius)
    best: int | None = None
    for index in range(search_start, search_end + 1):
        if text[index] not in STRONG_BREAK_CHARS + WEAK_BREAK_CHARS + " ":
            continue
        if best is None or abs(index - char_pos) < abs(best - char_pos):
            best = index
    return best


def _timed_pieces_from_words(
    segment: TranscriptSegment,
    pieces: list[str],
    words: list,
) -> list[TranscriptSegment] | None:
    text = segment.text
    word_chars = [max(len(word.text), 1) for word in words]
    total_word_chars = sum(word_chars)
    if total_word_chars <= 0 or not text:
        return None

    bounds: list[tuple[int, int]] = []
    pos = 0
    for piece in pieces:
        bounds.append((pos, pos + len(piece)))
        pos += len(piece)

    word_positions: list[int] = []
    acc = 0
    for word in words:
        word_positions.append(acc)
        acc += len(word.text) + 1

    def word_index_at(text_char_pos: int) -> int:
        for index, word_pos in enumerate(word_positions):
            if text_char_pos <= word_pos + len(words[index].text):
                return index
        return len(words) - 1

    results: list[TranscriptSegment] = []
    for index, (lo, hi) in enumerate(bounds):
        first = word_index_at(lo)
        last = max(first, min(word_index_at(hi), len(words) - 1))
        block_start = max(words[first].start, segment.start)
        block_end = min(words[last].end, segment.end)
        results.append(
            TranscriptSegment(
                index=segment.index + index,
                start=_round_seconds(block_start),
                end=_round_seconds(block_end),
                text=pieces[index],
            )
        )

    for index in range(1, len(results)):
        if results[index].start < results[index - 1].end:
            results[index].start = _round_seconds(results[index - 1].end)
    for result in results:
        if result.start >= result.end:
            return None
    return results


def _split_with_word_timestamps(
    segment: TranscriptSegment,
    target_count: int,
    max_length: int,
) -> list[TranscriptSegment] | None:
    words = list(segment.words)
    text = segment.text
    if target_count < 2 or len(words) < target_count or not text:
        return None

    pauses = [words[index + 1].start - words[index].end for index in range(len(words) - 1)]
    gap_count = target_count - 1
    cut_gaps = sorted(range(len(pauses)), key=lambda index: pauses[index], reverse=True)[:gap_count]
    cut_gaps = sorted(cut_gaps)

    word_chars = [max(len(word.text), 1) for word in words]
    total_word_chars = sum(word_chars)
    if total_word_chars <= 0:
        return None

    word_positions: list[int] = []
    acc = 0
    for word in words:
        word_positions.append(acc)
        acc += len(word.text) + 1
    total_with_spaces = max(acc - 1, 1)

    break_indexes: list[int] = []
    for gap in cut_gaps:
        char_pos = int(round(word_positions[gap + 1] / total_with_spaces * len(text)))
        break_index = _find_nearest_break_index(text, char_pos)
        if break_index is None:
            return None
        break_indexes.append(break_index)
    break_indexes = sorted(set(break_indexes))
    # 不同停顿映射到同一个断点（去重后刀数不足）时放弃词时间戳路径，
    # 交由带短块合并的加权 fallback 处理，避免少切一刀留下超长块。
    if len(break_indexes) != len(cut_gaps):
        return None

    pieces: list[str] = []
    previous = 0
    for break_index in break_indexes:
        piece = text[previous:break_index].strip()
        if not piece:
            return None
        pieces.append(piece)
        previous = break_index
    tail = text[previous:].strip()
    if not tail:
        return None
    pieces.append(tail)

    if " ".join(pieces) != " ".join(text.split()):
        return None
    if any(len(piece) > max_length for piece in pieces):
        return None
    # 词时间戳断点可能落在过短停顿处（如识别噪声单字），切出碎片块时放弃，
    # 由加权 fallback（带 _merge_short_pieces）合并。
    if any(_is_too_short_piece(piece) for piece in pieces):
        return None
    return _timed_pieces_from_words(segment, pieces, words)


def _distribute_times_evenly(segment: TranscriptSegment, pieces: list[str]) -> list[TranscriptSegment]:
    """Split a segment's time equally across pieces (last piece absorbs rounding).

    Used when enforcing the max-duration rule: equal time slices guarantee every
    piece stays within max_duration when the piece count is ceil(dur/max_duration),
    whereas length-weighted distribution can leave a long-text piece over the cap.
    """
    if len(pieces) == 1:
        return [
            TranscriptSegment(
                index=segment.index,
                start=_round_seconds(segment.start),
                end=_round_seconds(segment.end),
                text=pieces[0],
            )
        ]

    duration = max(segment.end - segment.start, 0.0)
    step = duration / len(pieces)
    results: list[TranscriptSegment] = []
    current_start = segment.start
    for piece_index, piece in enumerate(pieces):
        current_end = segment.end if piece_index == len(pieces) - 1 else current_start + step
        results.append(
            TranscriptSegment(
                index=segment.index + piece_index,
                start=_round_seconds(current_start),
                end=_round_seconds(current_end),
                text=piece,
            )
        )
        current_start = current_end
    return results


def _enforce_max_duration(
    segments: list[TranscriptSegment],
    settings: SubtitleSettings,
) -> list[TranscriptSegment]:
    """Re-split any piece that still exceeds max_duration (6-second rule).

    Runs after merging so that borrowing does not leave an over-long neighbor.
    Over-long pieces are re-cut with an equal time distribution, which keeps every
    resulting piece within max_duration regardless of text-length imbalance.
    """
    if settings.max_duration <= 0:
        return list(segments)

    result: list[TranscriptSegment] = []
    for segment in segments:
        duration = segment.end - segment.start
        if duration <= settings.max_duration + 0.1:
            result.append(segment)
            continue

        max_length = _cue_length_limit(segment.text)
        count = max(2, math.ceil(duration / settings.max_duration))
        pieces = _split_text_to_chunks(
            segment.text,
            max_length,
            max_pieces=count,
            desired_count=count,
        )
        if len(pieces) < 2:
            result.append(segment)
            continue
        result.extend(_enforce_max_duration(_distribute_times_evenly(segment, pieces), settings))
    return result


def _distribute_segment_times(segment: TranscriptSegment, pieces: list[str]) -> list[TranscriptSegment]:
    if len(pieces) == 1:
        return [
            TranscriptSegment(
                index=segment.index,
                start=_round_seconds(segment.start),
                end=_round_seconds(segment.end),
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
            current_end = _round_seconds(segment.end)
        else:
            current_end = _round_seconds(current_start + (duration * weights[piece_index] / total_weight))
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


def normalize_segments(
    segments: list[TranscriptSegment],
    settings: SubtitleSettings = DEFAULT_SUBTITLE_SETTINGS,
) -> list[TranscriptSegment]:
    merged_segments = _merge_short_segments(segments, settings.min_duration)
    normalized_segments: list[TranscriptSegment] = []

    for segment in merged_segments:
        cleaned_text = _normalize_whitespace(segment.text)
        if not cleaned_text:
            continue

        cleaned_segment = TranscriptSegment(
            index=segment.index,
            start=_round_seconds(segment.start),
            end=_round_seconds(segment.end),
            text=cleaned_text,
            words=segment.words,
        )

        if _should_split_segment(cleaned_segment, settings):
            max_length = _cue_length_limit(cleaned_text)
            target_count = _target_piece_count(cleaned_segment, settings)
            timed_segments = _split_with_word_timestamps(cleaned_segment, target_count, max_length)
            if timed_segments is not None and settings.max_duration > 0:
                if any(seg.end - seg.start > settings.max_duration + 0.1 for seg in timed_segments):
                    timed_segments = None
            if timed_segments is not None:
                split_segments = timed_segments
            else:
                split_segments = _distribute_segment_times(
                    cleaned_segment,
                    _split_text_to_chunks(
                        cleaned_text,
                        max_length,
                        max_pieces=max(target_count, MAX_SEGMENT_SPLITS),
                        desired_count=target_count,
                    ),
                )
        else:
            split_segments = [cleaned_segment]
        normalized_segments.extend(split_segments)

    # 拆分可能产出短块（如 raw 长段切出的残片），再做一遍最短时长合并
    normalized_segments = _merge_short_segments(normalized_segments, settings.min_duration)
    # 合并借时后可能留下超长块，按 6 秒规则兜底重切（时长均分）
    normalized_segments = _enforce_max_duration(normalized_segments, settings)

    if settings.gap_close:
        normalized_segments = _close_gaps(normalized_segments, settings.min_gap)

    reindexed_segments: list[TranscriptSegment] = []
    for index, segment in enumerate(normalized_segments, start=1):
        reindexed_segments.append(
            TranscriptSegment(
                index=index,
                start=_round_seconds(segment.start),
                end=_round_seconds(segment.end),
                text=segment.text,
            )
        )

    return reindexed_segments


def format_original_text(text: str) -> str:
    return _format_text_block(text, limit=_display_limit(text))


def format_translation_text(text: str) -> str:
    cleaned = sanitize_utf8_text(_normalize_whitespace(text))
    if _contains_cjk(cleaned) and _contains_latin(cleaned):
        return cleaned
    return _format_text_block(text, limit=_display_limit(text))


def _format_bilingual_original_text(text: str) -> str:
    return sanitize_utf8_text(_normalize_whitespace(text))


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
    subtitles: list[srt.Subtitle] = []

    for subtitle_index, (segment, translation) in enumerate(zip(segments, translations, strict=True), start=1):
        subtitles.append(
            srt.Subtitle(
                index=subtitle_index,
                start=_timedelta(segment.start),
                end=_timedelta(segment.end),
                content=format_translation_text(translation),
            )
        )

    return subtitles


def build_bilingual_subtitles(
    segments: list[TranscriptSegment],
    translations: list[str],
) -> list[srt.Subtitle]:
    subtitles: list[srt.Subtitle] = []

    for subtitle_index, (segment, translation) in enumerate(zip(segments, translations, strict=True), start=1):
        subtitles.append(
            srt.Subtitle(
                index=subtitle_index,
                start=_timedelta(segment.start),
                end=_timedelta(segment.end),
                content=_compose_bilingual_content(
                    format_translation_text(translation),
                    _format_bilingual_original_text(segment.text),
                ),
            )
        )

    return subtitles


def write_srt_file(path: str | Path, subtitles: Iterable[srt.Subtitle]) -> None:
    content = srt.compose(list(subtitles))
    safe_content = sanitize_utf8_text(content)
    Path(path).write_text(safe_content, encoding="utf-8")

