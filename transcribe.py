from dataclasses import dataclass, field
from pathlib import Path

from faster_whisper import WhisperModel

from config import AppConfig
from text_safety import sanitize_utf8_text


@dataclass(frozen=True)
class TranscriptWord:
    start: float
    end: float
    text: str


@dataclass
class TranscriptSegment:
    index: int
    start: float
    end: float
    text: str
    words: tuple[TranscriptWord, ...] = field(default_factory=tuple)


def _extract_transcript_words(raw_segment) -> tuple[TranscriptWord, ...]:
    results: list[TranscriptWord] = []
    for raw_word in getattr(raw_segment, "words", None) or ():
        word_text = sanitize_utf8_text(getattr(raw_word, "word", "")).strip()
        start = getattr(raw_word, "start", None)
        end = getattr(raw_word, "end", None)
        if not word_text or start is None or end is None:
            continue
        results.append(
            TranscriptWord(
                start=float(start),
                end=float(end),
                text=word_text,
            )
        )
    return tuple(results)


def transcribe_audio(audio_path: str | Path, config: AppConfig) -> list[TranscriptSegment]:
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"找不到音频文件: {path}")

    model = WhisperModel(
        model_size_or_path=config.normalized_whisper_model_size,
        device=config.whisper_device,
        compute_type=config.whisper_compute_type,
    )

    segments, _ = model.transcribe(
        str(path),
        language=config.effective_source_language,
        vad_filter=True,
        beam_size=config.whisper_beam_size,
        word_timestamps=config.whisper_word_timestamps,
    )

    results: list[TranscriptSegment] = []
    for index, segment in enumerate(segments, start=1):
        text = sanitize_utf8_text(segment.text).strip()
        if not text:
            continue
        results.append(
            TranscriptSegment(
                index=index,
                start=float(segment.start),
                end=float(segment.end),
                text=text,
                words=_extract_transcript_words(segment),
            )
        )

    if not results:
        raise ValueError("未识别到有效语音内容，请检查音频文件。")

    return results
