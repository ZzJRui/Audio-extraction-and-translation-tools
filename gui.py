import json
import os
import subprocess
import sys
from pathlib import Path

from config import AppConfig, get_app_root

APP_ROOT = get_app_root()
BACKEND_SCRIPT = APP_ROOT / "backend_runner.py"
SCENE_PRESETS = [
    "日常对话",
    "排球比赛解说",
    "体育赛事",
    "动漫字幕",
    "医学讲解",
]
TRANSLATION_MODES = {"translation", "bilingual"}

from PySide6.QtCore import QObject, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def sanitize_audio_path(audio_path: str | Path) -> Path:
    return Path(str(audio_path).strip().strip('"').strip("'"))


def validate_task_request(audio_path: str, subtitle_mode: str, scene: str | None) -> None:
    path = sanitize_audio_path(audio_path)
    if not str(path):
        raise ValueError("音频路径不能为空。")
    if not path.exists():
        raise FileNotFoundError(str(path))
    if subtitle_mode in TRANSLATION_MODES:
        if not (scene or "").strip():
            raise ValueError("翻译情景不能为空。")
        if not AppConfig().llm_api_key.strip():
            raise ValueError("未配置 LLM_API_KEY，无法生成译文或双语字幕。")


def build_error_message(exc: Exception) -> tuple[str, str | None]:
    if isinstance(exc, FileNotFoundError):
        return (
            f"处理失败：找不到音频文件：{exc}",
            "建议：请检查路径是否正确，Windows 路径可以直接粘贴，带引号也可以。",
        )
    if isinstance(exc, PermissionError):
        return (
            "处理失败：文件正在被占用，或者当前程序没有访问权限。",
            "建议：请关闭占用该文件的程序后重试。",
        )
    if isinstance(exc, ValueError):
        return (f"处理失败：{exc}", None)
    return (
        f"处理失败：{exc}",
        "建议：请重试一次；如果问题持续存在，再把错误提示发给我。",
    )


def parse_backend_error(stderr_text: str) -> tuple[str, str | None]:
    text = stderr_text.strip() or "后端返回了空错误信息。"
    if text.startswith("FileNotFoundError:"):
        return build_error_message(FileNotFoundError(text.split(":", 1)[1].strip()))
    if text.startswith("ValueError:"):
        return build_error_message(ValueError(text.split(":", 1)[1].strip()))
    lowered = text.lower()
    if "authentication" in lowered or "api key" in lowered or "unauthorized" in lowered:
        return ("处理失败：翻译接口认证失败。", "建议：请检查 .env 里的 LLM_API_KEY 是否正确。")
    if "timeout" in lowered or "connection" in lowered:
        return ("处理失败：无法连接翻译服务。", "建议：请检查当前网络，或稍后再试。")
    if "rate limit" in lowered or "quota" in lowered:
        return ("处理失败：翻译接口请求过于频繁，或当前额度不足。", "建议：请稍后重试，或检查 API 账户额度。")
    if "ffmpeg" in lowered:
        return ("处理失败：未检测到可用的 ffmpeg。", "建议：请确认项目的 ffmpeg 工具目录完整，或把 ffmpeg 加入 PATH。")
    return (f"处理失败：{text}", "建议：请查看网络、模型配置和依赖环境后重试。")


def prepare_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in output_dir.iterdir():
        if child.is_file():
            child.unlink()


class TaskWorker(QObject):
    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, audio_path: str, subtitle_mode: str, scene: str | None) -> None:
        super().__init__()
        self.audio_path = audio_path
        self.subtitle_mode = subtitle_mode
        self.scene = scene

    @Slot()
    def run(self) -> None:
        try:
            output_dir = AppConfig().output_dir
            self.progress.emit("正在清理上一轮任务留下的输出文件...")
            prepare_output_dir(output_dir)
            self.progress.emit("清理完成。")

            payload = {
                "audio_path": self.audio_path,
                "subtitle_mode": self.subtitle_mode,
                "scene": self.scene,
            }
            backend_python = os.environ.get("BACKEND_PYTHON", sys.executable)
            self.progress.emit("任务已开始，请稍候...")
            result = subprocess.run(
                [backend_python, str(BACKEND_SCRIPT)],
                input=json.dumps(payload, ensure_ascii=False),
                text=True,
                capture_output=True,
                cwd=str(APP_ROOT),
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode != 0:
                message, suggestion = parse_backend_error(result.stderr)
                self.failed.emit(message if not suggestion else f"{message}\n{suggestion}")
                return

            raw = json.loads(result.stdout)
            self.finished.emit(raw)
        except Exception as exc:
            message, suggestion = build_error_message(exc)
            self.failed.emit(message if not suggestion else f"{message}\n{suggestion}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.output_dir = AppConfig().output_dir
        self.worker_thread: QThread | None = None
        self.worker: TaskWorker | None = None

        self.setWindowTitle("音频字幕提取与翻译工具")
        self.resize(1180, 760)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("音频字幕提取与翻译工具")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        subtitle = QLabel("选择音频、设置字幕类型和翻译情景后，一键生成本次字幕文件。")
        subtitle.setStyleSheet("color: #4b5563;")
        self.status_label = QLabel("准备就绪。")
        self.status_label.setStyleSheet(
            "padding: 8px 12px; background: #eef6ff; border: 1px solid #cfe3ff; border-radius: 6px;"
        )
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.status_label)

        body = QHBoxLayout()
        body.setSpacing(14)
        layout.addLayout(body, 1)
        left = self._build_left_panel()
        right = self._build_right_panel()
        left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body.addWidget(left, 4)
        body.addWidget(right, 6)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.open_output_button = QPushButton("打开输出目录")
        self.reset_button = QPushButton("重新开始")
        self.exit_button = QPushButton("退出")
        footer.addWidget(self.open_output_button)
        footer.addWidget(self.reset_button)
        footer.addWidget(self.exit_button)
        layout.addLayout(footer)

        self._connect_signals()
        self._update_scene_enabled()

    def _build_left_panel(self) -> QWidget:
        group = QGroupBox("任务配置")
        layout = QVBoxLayout(group)
        layout.setSpacing(14)

        form = QFormLayout()
        row = QHBoxLayout()
        self.audio_path_edit = QLineEdit()
        self.audio_path_edit.setPlaceholderText("请选择音频文件，支持 mp3 / wav / m4a / flac / aac")
        self.browse_button = QPushButton("浏览音频")
        row.addWidget(self.audio_path_edit, 1)
        row.addWidget(self.browse_button)
        form.addRow("音频文件", row)
        layout.addLayout(form)

        mode_group = QGroupBox("字幕类型")
        mode_layout = QVBoxLayout(mode_group)
        self.original_radio = QRadioButton("原文字幕")
        self.translation_radio = QRadioButton("译文字幕")
        self.bilingual_radio = QRadioButton("双语字幕")
        self.bilingual_radio.setChecked(True)
        for button in [self.original_radio, self.translation_radio, self.bilingual_radio]:
            mode_layout.addWidget(button)
        layout.addWidget(mode_group)

        scene_form = QFormLayout()
        self.scene_combo = QComboBox()
        self.scene_combo.setEditable(True)
        self.scene_combo.addItems(SCENE_PRESETS)
        scene_form.addRow("翻译情景", self.scene_combo)
        layout.addLayout(scene_form)

        tips = QLabel("桌面版每次开始任务前只清理 output 目录，不会删除你选择的原始音频。")
        tips.setWordWrap(True)
        tips.setStyleSheet("color: #6b7280;")
        layout.addWidget(tips)

        self.start_button = QPushButton("开始生成")
        self.start_button.setMinimumHeight(40)
        self.start_button.setStyleSheet(
            "font-size: 15px; font-weight: 600; background: #2563eb; color: white; border-radius: 8px;"
        )
        layout.addStretch(1)
        layout.addWidget(self.start_button)
        return group

    def _build_right_panel(self) -> QWidget:
        group = QGroupBox("结果与日志")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        form = QFormLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setReadOnly(True)
        form.addRow("输出文件", self.output_path_edit)
        layout.addLayout(form)

        self.output_list = QListWidget()
        self.output_list.setMaximumHeight(80)
        layout.addWidget(self.output_list)

        layout.addWidget(QLabel("运行日志"))
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setPlaceholderText("运行过程会显示在这里。")
        layout.addWidget(self.log_edit, 1)

        layout.addWidget(QLabel("字幕预览"))
        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setPlaceholderText("生成完成后，这里会显示本次字幕内容。")
        layout.addWidget(self.preview_edit, 2)
        return group

    def _connect_signals(self) -> None:
        self.browse_button.clicked.connect(self._browse_audio)
        self.start_button.clicked.connect(self._start_task)
        self.reset_button.clicked.connect(self._reset_form)
        self.open_output_button.clicked.connect(self._open_output_dir)
        self.exit_button.clicked.connect(self.close)
        self.output_list.itemDoubleClicked.connect(self._open_selected_output)
        self.original_radio.toggled.connect(self._update_scene_enabled)
        self.translation_radio.toggled.connect(self._update_scene_enabled)
        self.bilingual_radio.toggled.connect(self._update_scene_enabled)

    def _current_mode(self) -> str:
        if self.original_radio.isChecked():
            return "original"
        if self.translation_radio.isChecked():
            return "translation"
        return "bilingual"

    def _update_scene_enabled(self) -> None:
        self.scene_combo.setEnabled(self._current_mode() in TRANSLATION_MODES)

    def _append_log(self, message: str) -> None:
        self.log_edit.appendPlainText(message)
        self.status_label.setText(message)

    def _set_form_enabled(self, enabled: bool) -> None:
        self.audio_path_edit.setEnabled(enabled)
        self.browse_button.setEnabled(enabled)
        self.original_radio.setEnabled(enabled)
        self.translation_radio.setEnabled(enabled)
        self.bilingual_radio.setEnabled(enabled)
        self.scene_combo.setEnabled(enabled and self._current_mode() in TRANSLATION_MODES)
        self.start_button.setEnabled(enabled)
        self.reset_button.setEnabled(enabled)

    def _reset_result_area(self) -> None:
        self.output_path_edit.clear()
        self.output_list.clear()
        self.preview_edit.clear()
        self.log_edit.clear()

    @Slot()
    def _browse_audio(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择音频文件",
            str(APP_ROOT),
            "音频文件 (*.mp3 *.wav *.m4a *.flac *.aac);;所有文件 (*.*)",
        )
        if file_path:
            self.audio_path_edit.setText(file_path)

    @Slot()
    def _start_task(self) -> None:
        audio_path = self.audio_path_edit.text().strip().strip('"').strip("'")
        subtitle_mode = self._current_mode()
        scene = self.scene_combo.currentText().strip() if subtitle_mode in TRANSLATION_MODES else None

        try:
            validate_task_request(audio_path, subtitle_mode, scene)
        except Exception as exc:
            message, suggestion = build_error_message(exc)
            QMessageBox.critical(self, "无法开始任务", message if not suggestion else f"{message}\n{suggestion}")
            return

        self._reset_result_area()
        self._set_form_enabled(False)
        self.status_label.setText("任务已开始，请稍候...")

        self.worker_thread = QThread(self)
        self.worker = TaskWorker(audio_path, subtitle_mode, scene)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._append_log)
        self.worker.finished.connect(self._handle_success)
        self.worker.failed.connect(self._handle_failure)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self._on_thread_finished)
        self.worker_thread.start()

    @Slot(object)
    def _handle_success(self, result: dict) -> None:
        output_file = Path(result["output_file"])
        self.output_path_edit.setText(str(output_file.resolve()))
        self.output_list.addItem(output_file.name)
        if output_file.exists():
            self.preview_edit.setPlainText(output_file.read_text(encoding="utf-8"))
        self._append_log("任务完成。")
        QMessageBox.information(
            self,
            "生成完成",
            f"已生成 {output_file.name}\n输出目录：{Path(result['output_dir']).resolve()}",
        )

    @Slot(str)
    def _handle_failure(self, message: str) -> None:
        self._append_log(message.replace("\n", " "))
        QMessageBox.critical(self, "处理失败", message)

    @Slot()
    def _on_thread_finished(self) -> None:
        self._set_form_enabled(True)
        self.worker = None
        self.worker_thread = None

    @Slot()
    def _open_output_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_dir.resolve())))

    @Slot()
    def _reset_form(self) -> None:
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.information(self, "任务进行中", "当前任务正在执行，请等待完成后再重置。")
            return
        self.audio_path_edit.clear()
        self.bilingual_radio.setChecked(True)
        self.scene_combo.setCurrentText(SCENE_PRESETS[0])
        self._update_scene_enabled()
        self._reset_result_area()
        self.status_label.setText("准备就绪。")

    @Slot()
    def _open_selected_output(self, item) -> None:
        output_file = self.output_dir / item.text()
        if output_file.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_file.resolve())))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.information(self, "任务进行中", "当前任务正在执行，请等待完成后再退出。")
            event.ignore()
            return
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
