import os
import sys
from dataclasses import dataclass
from pathlib import Path


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_runtime_root() -> Path:
    env_value = os.getenv("APP_RUNTIME_ROOT", "").strip()
    if env_value:
        return Path(env_value)
    app_root = get_app_root()
    return app_root.parent / f"{app_root.name}_runtime"


def load_dotenv(dotenv_path: str | Path | None = None) -> None:
    env_file = Path(dotenv_path) if dotenv_path else get_app_root() / ".env"
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def save_env_value(key: str, value: str, dotenv_path: str | Path | None = None) -> None:
    env_file = Path(dotenv_path) if dotenv_path else get_app_root() / ".env"
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
    whisper_model_size: str = os.getenv("WHISPER_MODEL_SIZE", "small")
    whisper_device: str = os.getenv("WHISPER_DEVICE", "auto")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "auto")
    source_language: str | None = os.getenv("SOURCE_LANGUAGE") or None
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    translation_batch_size: int = int(os.getenv("TRANSLATION_BATCH_SIZE", "12"))
    output_dir_name: str = os.getenv("OUTPUT_DIR", "output")

    @property
    def output_dir(self) -> Path:
        return get_app_root() / self.output_dir_name
