from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel

from config import AppConfig
from text_safety import sanitize_utf8_text


@dataclass
class TranscriptSegment:
    index: int
    start: float
    end: float
    text: str


def transcribe_audio(audio_path: str | Path, config: AppConfig) -> list[TranscriptSegment]:
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"找不到音频文件: {path}")

    model = WhisperModel(
        model_size_or_path=config.whisper_model_size,
        device=config.whisper_device,
        compute_type=config.whisper_compute_type,
    )

    segments, _ = model.transcribe(
        str(path),
        language=config.source_language,
        vad_filter=True,
        beam_size=5,
        word_timestamps=False,
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
            )
        )

    if not results:
        raise ValueError("未识别到有效语音内容，请检查音频文件。")

    return results

