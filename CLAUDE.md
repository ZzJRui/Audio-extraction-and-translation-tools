# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

### Python environment
- Install Python dependencies:
  - `pip install -r requirements.txt`
- Runtime-only Python dependencies:
  - `pip install -r requirements-runtime.txt`

### Electron / desktop workbench
- Install Node dependencies:
  - `npm install`
- Start the Electron workbench in development:
  - `npm start`
- Build bundled runtime used by Electron packaging:
  - `npm run build:runtime`
- Build unpacked Windows app for smoke testing:
  - `npm run dist:win:dir`
- Build Windows NSIS installer:
  - `npm run dist:win`
- Run Electron tests:
  - `npm run test:electron`
- Syntax-check Electron entrypoints and shared modules:
  - `npm run check:electron`

### Python tests
- Run all Python tests:
  - `python -m unittest discover -s tests -v`
- Run a single test module:
  - `python -m unittest tests.test_subtitle_pipeline -v`
- Run a single test case:
  - `python -m unittest tests.test_subtitle_pipeline.SubtitlePipelineTests -v`
- Run a single test method:
  - `python -m unittest tests.test_subtitle_pipeline.SubtitlePipelineTests.test_execute_task_translates_normalized_segments_before_translation -v`

### Local app entrypoints
- Preferred Windows launcher for the Electron UI:
  - `run_electron.bat`
- Legacy Python GUI fallback:
  - `run_gui.bat`
- Direct backend task runner reads JSON from stdin and writes JSON to stdout:
  - `python backend_runner.py`

## High-level architecture

This repository is an audio-to-subtitle desktop application with a Python subtitle pipeline and an Electron-first desktop shell. The Python backend remains the only execution engine for transcription, translation, and subtitle export; Electron is a task orchestration and presentation layer over that backend.

### Execution flow
1. UI collects `audio_path`, `subtitle_mode`, and optional `scene`.
2. Electron or the legacy GUI launches `backend_runner.py` as a subprocess.
3. `backend_runner.py` performs startup checks, runs `execute_subtitle_task()` from `app_service.py`, streams progress on stderr using the `__PROGRESS__:` prefix, and returns a JSON result on stdout.
4. `app_service.py` owns the end-to-end subtitle task orchestration:
   - initialize runtime
   - validate inputs and environment
   - transcribe audio
   - normalize transcript segments
   - optionally translate normalized segments
   - build and write `original.srt`, `translation.srt`, or `bilingual.srt`
5. The UI reads the JSON result and displays output path, preview text, and task metadata.

### Python backend responsibilities
- `app_service.py`
  - Main orchestration layer.
  - `TaskResult` is the contract returned to GUI/Electron callers.
  - This is the place to change pipeline order or task result fields.
- `transcribe.py`
  - Wraps `faster-whisper`.
  - Produces `TranscriptSegment` and optional word-level timestamps (`TranscriptWord`).
  - Source language defaults to English unless overridden in `.env`.
- `subtitle.py`
  - Owns subtitle segmentation and formatting.
  - `normalize_segments()` is the source-of-truth segmentation step used before translation/output.
  - Builders convert normalized segments into SRT subtitles for original / translation / bilingual modes.
  - Formatting helpers enforce line-length and readability constraints.
- `translate.py`
  - Batches normalized subtitle units for LLM translation.
  - Uses JSON-only responses with `id -> translation` mapping and retry logic for missing items.
  - Contains terminology normalization for subtitle-domain wording.
- `config.py`
  - Centralizes `.env` loading, runtime path resolution, Whisper/LLM settings, and output directory selection.
- `stability.py`
  - Startup diagnostics and environment preparation.
  - Important when working on packaged/runtime behavior.
- `backend_runner.py`
  - Process boundary for GUI/Electron integration.
  - Converts `TaskResult` dataclass output into JSON-safe paths and emits diagnostic logs.

### UI layers
- `electron/src/main/`
  - Main-process code for window creation, runtime path resolution, Python process launching, and OS integrations.
  - `python-task.js` is the bridge between Electron and the Python backend.
  - `runtime-paths.js` is the packaged-vs-development path contract.
- `electron/src/preload` / `electron/src/renderer/`
  - Preload exposes the constrained IPC surface.
  - Renderer implements the three-column workbench, state updates, logs, and subtitle preview.
- `gui.py`
  - Legacy Python GUI.
  - Prefers PySide6, falls back to Tkinter if Qt is unavailable.
  - Still useful for compatibility/debugging, but Electron is the primary UI path.

### Path model
The codebase distinguishes three roots, especially for packaged Electron builds:
- `bundle root`: read-only application resources
- `data root`: user-writable state such as `.env`, `output/`, logs
- `runtime root`: cache, temp files, model/runtime assets

This path split is important when changing packaging, ffmpeg discovery, output locations, or `.env` loading. `config.py` and `electron/src/main/runtime-paths.js` must stay conceptually aligned.

### Current subtitle pipeline contract
The pipeline is segment-first:
- transcription returns raw Whisper segments
- `normalize_segments()` converts them into the actual subtitle units used by all modes
- translation runs on normalized segments, not raw Whisper chunks
- translation and bilingual outputs are structurally 1:1 with normalized segments at the cue/time-range level
- cue-internal wrapping is allowed, but builders should not re-split normalized segments into additional timed sub-cues unless the pipeline contract is intentionally changed

Segmentation is duration/reading-speed driven (Netflix/BBC/DCMP-inspired, tunable via `SubtitleSettings` / `.env`):
- a subtitle is split only when it exceeds 2×42 chars per screen, its text/duration ratio exceeds `SUBTITLE_MAX_CPS` (default 15 ≈ 170 wpm), or its duration exceeds `SUBTITLE_MAX_DURATION` (6-second rule)
- short raw segments (< `SUBTITLE_MIN_DURATION` ≈ 0.8s, or ≤2 words with little time) are merged into neighbors (borrowing time)
- word-level timestamps (`TranscriptSegment.words`) pick pause-based break points; falling back to length-weighted splits when unavailable
- small gaps between subtitles (< `SUBTITLE_MIN_GAP` ≈ 0.5s) are closed (chaining) when `SUBTITLE_GAP_CLOSE` is on

If output still looks like old long-segment back-splitting artifacts, verify that the SRT file was regenerated after the segment-first refactor; stale `output/*.srt` files may still reflect the previous pipeline.

## Environment and runtime assumptions
- Development is Windows-first.
- README expects Python 3.13 and Node.js 18+.
- `ffmpeg` must be available on PATH for development, or bundled into the Electron runtime for packaged builds.
- Translation and bilingual modes require `.env` values for:
  - `LLM_API_KEY`
  - `LLM_BASE_URL`
  - `LLM_MODEL`
- Original subtitle mode does not require LLM credentials.

## Testing notes that matter for changes
- Python tests use `unittest`, not pytest.
- `tests/test_subtitle_pipeline.py` validates orchestration and normalized-segment behavior.
- `tests/test_subtitle_readability.py` covers line breaking and subtitle readability constraints.
- `tests/test_translation_retries.py` and `tests/test_translation_terminology.py` lock in translation retry/terminology behavior.
- `tests/test_surrogate_sanitization.py` protects UTF-8-safe subtitle writing.
- Electron checks are intentionally lightweight: syntax checks plus `node --test` coverage under `electron/tests/`.

When changing the subtitle pipeline, read `app_service.py`, `subtitle.py`, `translate.py`, and the subtitle-related tests together; the behavior is defined across those files rather than in a single module.
