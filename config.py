import os
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_WHISPER_MODEL_SIZE = "small"
DEFAULT_SOURCE_LANGUAGE = "en"
DEFAULT_WHISPER_BEAM_SIZE = 5
DEFAULT_WHISPER_WORD_TIMESTAMPS = True

DEFAULT_SUBTITLE_MAX_CPS = 15.0
DEFAULT_SUBTITLE_MIN_DURATION = 0.8
DEFAULT_SUBTITLE_MAX_DURATION = 6.0
DEFAULT_SUBTITLE_MIN_GAP = 0.5
DEFAULT_SUBTITLE_GAP_CLOSE = True


def get_bundle_root() -> Path:
    env_value = os.getenv("APP_BUNDLE_ROOT", "").strip()
    if env_value:
        return Path(env_value)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_app_root() -> Path:
    return get_bundle_root()


def get_data_root() -> Path:
    env_value = os.getenv("APP_DATA_ROOT", "").strip()
    if env_value:
        return Path(env_value)
    return get_bundle_root()


def get_runtime_root() -> Path:
    env_value = os.getenv("APP_RUNTIME_ROOT", "").strip()
    if env_value:
        return Path(env_value)

    data_root = get_data_root()
    bundle_root = get_bundle_root()
    if data_root != bundle_root:
        return data_root / "runtime"

    return bundle_root.parent / f"{bundle_root.name}_runtime"


def get_env_file_path() -> Path:
    return get_data_root() / ".env"


def get_env_template_path() -> Path:
    return get_bundle_root() / ".env.example"


def load_dotenv(dotenv_path: str | Path | None = None) -> None:
    env_file = Path(dotenv_path) if dotenv_path else get_env_file_path()
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def save_env_value(key: str, value: str, dotenv_path: str | Path | None = None) -> None:
    env_file = Path(dotenv_path) if dotenv_path else get_env_file_path()
    env_file.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()

    updated = False
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        existing_key, _ = line.split("=", 1)
        if existing_key.strip() == key:
            lines[index] = f"{key}={value}"
            updated = True
            break

    if not updated:
        lines.append(f"{key}={value}")

    env_file.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    os.environ[key] = value


load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    whisper_model_size: str = os.getenv("WHISPER_MODEL_SIZE", DEFAULT_WHISPER_MODEL_SIZE)
    whisper_device: str = os.getenv("WHISPER_DEVICE", "auto")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "auto")
    source_language: str | None = os.getenv("SOURCE_LANGUAGE") or None
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    translation_batch_size: int = int(os.getenv("TRANSLATION_BATCH_SIZE", "12"))
    output_dir_name: str = os.getenv("OUTPUT_DIR", "output")
    subtitle_max_cps: float = float(os.getenv("SUBTITLE_MAX_CPS", str(DEFAULT_SUBTITLE_MAX_CPS)))
    subtitle_min_duration: float = float(os.getenv("SUBTITLE_MIN_DURATION", str(DEFAULT_SUBTITLE_MIN_DURATION)))
    subtitle_max_duration: float = float(os.getenv("SUBTITLE_MAX_DURATION", str(DEFAULT_SUBTITLE_MAX_DURATION)))
    subtitle_min_gap: float = float(os.getenv("SUBTITLE_MIN_GAP", str(DEFAULT_SUBTITLE_MIN_GAP)))
    subtitle_gap_close: bool = (
        os.getenv("SUBTITLE_GAP_CLOSE", "true").strip().lower() in ("1", "true", "yes", "on")
    )

    @property
    def normalized_whisper_model_size(self) -> str:
        model_size = (self.whisper_model_size or "").strip()
        if not model_size:
            return DEFAULT_WHISPER_MODEL_SIZE
        if any(sep in model_size for sep in ("/", "\\")) or Path(model_size).exists():
            return model_size
        return model_size.lower()

    @property
    def effective_source_language(self) -> str:
        source_language = (self.source_language or "").strip().lower()
        return source_language or DEFAULT_SOURCE_LANGUAGE

    @property
    def whisper_beam_size(self) -> int:
        return DEFAULT_WHISPER_BEAM_SIZE

    @property
    def whisper_word_timestamps(self) -> bool:
        return DEFAULT_WHISPER_WORD_TIMESTAMPS

    @property
    def output_dir(self) -> Path:
        target = Path(self.output_dir_name)
        if target.is_absolute():
            return target
        return get_data_root() / target
