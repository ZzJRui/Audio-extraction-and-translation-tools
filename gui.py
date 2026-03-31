import os
import queue
import sys
import threading
import webbrowser
from pathlib import Path

from backend_client import BackendProcessError, run_backend_task
from config import AppConfig, get_app_root
from error_messages import build_gui_error_message, parse_backend_error
from stability import collect_startup_report, format_startup_report, prepare_runtime_environment

APP_ROOT = get_app_root()
BACKEND_SCRIPT = APP_ROOT / "backend_runner.py"
APP_TITLE = "音频字幕提取与翻译工具"
APP_SUBTITLE = "选择音频、字幕类型和翻译场景后，一键生成本次字幕文件。"
READY_STATUS = "准备就绪。"
SCENE_PRESETS = ["日常对话", "排球教学场景", "体育赛事", "动漫字幕", "医学讲解"]
TRANSLATION_MODES = {"translation", "bilingual"}
SAFE_FIXED_FONT_FAMILIES = (
    "Consolas",
    "Cascadia Mono",
    "Cascadia Code",
    "Courier New",
    "Lucida Console",
)

prepare_runtime_environment(APP_ROOT)


def _candidate_conda_prefixes() -> list[Path]:
    prefixes: list[Path] = []
    env_prefix = os.environ.get("CONDA_PREFIX", "").strip()
    if env_prefix:
        prefixes.append(Path(env_prefix))
    executable_prefix = Path(sys.executable).resolve().parent
    if (executable_prefix / "conda-meta").exists():
        prefixes.append(executable_prefix)
    seen: set[str] = set()
    result: list[Path] = []
    for prefix in prefixes:
        key = str(prefix.resolve())
        if key in seen or not prefix.exists():
            continue
        seen.add(key)
        result.append(prefix)
    return result


def _prepare_pyside6_runtime() -> None:
    for prefix in _candidate_conda_prefixes():
        pkg_dir = prefix / "pkgs"
        if pkg_dir.exists():
            for candidate in sorted(pkg_dir.glob("pyside6-*"), key=lambda p: p.name, reverse=True):
                site_packages = candidate / "Lib" / "site-packages"
                if (site_packages / "PySide6").exists() and str(site_packages) not in sys.path:
                    sys.path.insert(0, str(site_packages))
                    break
        library_bin = prefix / "Library" / "bin"
        if not library_bin.exists():
            continue
        bin_str = str(library_bin)
        if bin_str not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = bin_str + os.pathsep + os.environ.get("PATH", "")
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is not None:
            try:
                add_dll_directory(bin_str)
            except (FileNotFoundError, OSError):
                pass


_prepare_pyside6_runtime()
GUI_BACKEND = "pyside6"
GUI_IMPORT_ERROR: Exception | None = None

try:
    from PySide6.QtCore import QObject, QThread, Signal, Slot
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QRadioButton,
        QVBoxLayout,
        QWidget,
    )
except Exception as exc:  # pragma: no cover
    GUI_BACKEND = "tkinter"
    GUI_IMPORT_ERROR = exc
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText


def choose_safe_fixed_font_family(preferred_family: str | None, available_families: list[str]) -> str | None:
    normalized = {family.casefold(): family for family in available_families if family}
    preferred_key = (preferred_family or "").strip().casefold()
    if preferred_key and preferred_key != "fixedsys" and preferred_key in normalized:
        return normalized[preferred_key]
    for candidate in SAFE_FIXED_FONT_FAMILIES:
        match = normalized.get(candidate.casefold())
        if match:
            return match
    return None


def _apply_safe_qt_font_policy() -> "QFont | None":
    if GUI_BACKEND != "pyside6":
        return None
    app = QApplication.instance()
    if app is None:
        return None
    try:
        preferred_family = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
        safe_family = choose_safe_fixed_font_family(preferred_family, list(QFontDatabase.families()))
    except Exception:
        return None
    if not safe_family:
        return None
    font = QFont(safe_family)
    font.setStyleHint(QFont.StyleHint.Monospace)
    QApplication.setFont(font, "QPlainTextEdit")
    QApplication.setFont(font, "QTextEdit")
    return font


def sanitize_audio_path(audio_path: str | Path) -> Path:
    return Path(str(audio_path).strip().strip('"').strip("'"))


def validate_task_request(audio_path: str, subtitle_mode: str, scene: str | None) -> None:
    path = sanitize_audio_path(audio_path)
    if not str(path):
        raise ValueError("音频路径不能为空。")
    if not path.exists():
        raise FileNotFoundError(str(path))
    if subtitle_mode in TRANSLATION_MODES and not (scene or "").strip():
        raise ValueError("翻译场景不能为空。")


def build_startup_report(subtitle_mode: str | None = None):
    prepare_runtime_environment(APP_ROOT)
    return collect_startup_report(AppConfig(), gui_backend=GUI_BACKEND, subtitle_mode=subtitle_mode)


def build_startup_report_message(report) -> str:
    return "\n".join(format_startup_report(report, levels={"fatal", "warning"}))


def execute_gui_task(audio_path: str, subtitle_mode: str, scene: str | None, *, progress_callback) -> dict:
    payload = {
        "audio_path": audio_path,
        "subtitle_mode": subtitle_mode,
        "scene": scene,
        "gui_backend": GUI_BACKEND,
    }
    progress_callback("任务已开始，请稍候...")
    return run_backend_task(
        backend_python=os.environ.get("BACKEND_PYTHON", sys.executable),
        backend_script=BACKEND_SCRIPT,
        app_root=APP_ROOT,
        payload=payload,
        progress_callback=progress_callback,
    )


def open_path(path: Path) -> None:
    resolved = path.resolve()
    if sys.platform.startswith("win"):
        os.startfile(str(resolved))  # type: ignore[attr-defined]
    else:
        webbrowser.open(resolved.as_uri())


if GUI_BACKEND == "pyside6":
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
                self.finished.emit(
                    execute_gui_task(
                        self.audio_path,
                        self.subtitle_mode,
                        self.scene,
                        progress_callback=self.progress.emit,
                    )
                )
            except BackendProcessError as exc:
                message, suggestion = parse_backend_error(exc.stderr_text)
                self.failed.emit(message if not suggestion else f"{message}\n{suggestion}")
            except Exception as exc:
                message, suggestion = build_gui_error_message(exc)
                self.failed.emit(message if not suggestion else f"{message}\n{suggestion}")


    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            fixed_text_font = _apply_safe_qt_font_policy()
            self.output_dir = AppConfig().output_dir
            self.worker_thread: QThread | None = None
            self.worker: TaskWorker | None = None
            self.startup_blocked = False
            self.setWindowTitle(APP_TITLE)
            self.resize(1180, 760)

            root = QWidget()
            self.setCentralWidget(root)
            layout = QVBoxLayout(root)

            title = QLabel(APP_TITLE)
            subtitle = QLabel(APP_SUBTITLE)
            self.status_label = QLabel(READY_STATUS)
            layout.addWidget(title)
            layout.addWidget(subtitle)
            layout.addWidget(self.status_label)

            row = QHBoxLayout()
            self.audio_path_edit = QLineEdit()
            self.browse_button = QPushButton("浏览音频")
            row.addWidget(self.audio_path_edit, 1)
            row.addWidget(self.browse_button)
            layout.addLayout(row)

            mode_row = QHBoxLayout()
            self.original_radio = QRadioButton("原文字幕")
            self.translation_radio = QRadioButton("译文字幕")
            self.bilingual_radio = QRadioButton("双语字幕")
            self.bilingual_radio.setChecked(True)
            for button in [self.original_radio, self.translation_radio, self.bilingual_radio]:
                mode_row.addWidget(button)
            layout.addLayout(mode_row)

            self.scene_combo = QComboBox()
            self.scene_combo.setEditable(True)
            self.scene_combo.addItems(SCENE_PRESETS)
            layout.addWidget(self.scene_combo)

            self.start_button = QPushButton("开始生成")
            layout.addWidget(self.start_button)

            self.output_path_edit = QLineEdit()
            self.output_path_edit.setReadOnly(True)
            self.output_list = QListWidget()
            self.log_edit = QPlainTextEdit()
            self.log_edit.setReadOnly(True)
            self.preview_edit = QPlainTextEdit()
            self.preview_edit.setReadOnly(True)
            if fixed_text_font is not None:
                self.log_edit.setFont(fixed_text_font)
                self.preview_edit.setFont(fixed_text_font)

            layout.addWidget(self.output_path_edit)
            layout.addWidget(self.output_list)
            layout.addWidget(self.log_edit, 1)
            layout.addWidget(self.preview_edit, 1)

            footer = QHBoxLayout()
            self.open_output_button = QPushButton("打开输出目录")
            self.reset_button = QPushButton("重新开始")
            self.exit_button = QPushButton("退出")
            footer.addWidget(self.open_output_button)
            footer.addWidget(self.reset_button)
            footer.addWidget(self.exit_button)
            layout.addLayout(footer)

            self.browse_button.clicked.connect(self._browse_audio)
            self.start_button.clicked.connect(self._start_task)
            self.reset_button.clicked.connect(self._reset_form)
            self.open_output_button.clicked.connect(lambda: open_path(self.output_dir))
            self.exit_button.clicked.connect(self.close)
            self.output_list.itemDoubleClicked.connect(lambda item: open_path(self.output_dir / item.text()))
            self.original_radio.toggled.connect(self._update_scene_enabled)
            self.translation_radio.toggled.connect(self._update_scene_enabled)
            self.bilingual_radio.toggled.connect(self._update_scene_enabled)
            self._update_scene_enabled()
            self._show_startup_summary(build_startup_report(), startup=True)

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

        def _show_startup_summary(self, report, *, startup: bool) -> None:
            for line in format_startup_report(report):
                self._append_log(line)
            if report.has_fatal:
                if startup:
                    self.startup_blocked = True
                    self.start_button.setEnabled(False)
                QMessageBox.critical(
                    self,
                    "启动自检未通过" if startup else "任务前检查未通过",
                    build_startup_report_message(report),
                )

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
                message, suggestion = build_gui_error_message(exc)
                QMessageBox.critical(self, "无法开始任务", message if not suggestion else f"{message}\n{suggestion}")
                return

            self.output_path_edit.clear()
            self.output_list.clear()
            self.preview_edit.clear()
            self.log_edit.clear()

            report = build_startup_report(subtitle_mode)
            self.startup_blocked = False
            self._show_startup_summary(report, startup=False)
            if report.has_fatal:
                return

            self.start_button.setEnabled(False)
            self.worker_thread = QThread(self)
            self.worker = TaskWorker(audio_path, subtitle_mode, scene)
            self.worker.moveToThread(self.worker_thread)
            self.worker_thread.started.connect(self.worker.run)
            self.worker.progress.connect(self._append_log)
            self.worker.finished.connect(self._handle_success)
            self.worker.failed.connect(self._handle_failure)
            self.worker.finished.connect(self.worker_thread.quit)
            self.worker.failed.connect(self.worker_thread.quit)
            self.worker_thread.finished.connect(lambda: self.start_button.setEnabled(True))
            self.worker_thread.finished.connect(self.worker_thread.deleteLater)
            self.worker_thread.start()

        @Slot(object)
        def _handle_success(self, result: dict) -> None:
            output_file = Path(result["output_file"])
            self.output_path_edit.setText(str(output_file.resolve()))
            self.output_list.addItem(output_file.name)
            if output_file.exists():
                self.preview_edit.setPlainText(output_file.read_text(encoding="utf-8"))
            self._append_log("任务完成。")

        @Slot(str)
        def _handle_failure(self, message: str) -> None:
            self._append_log(message.replace("\n", " "))
            QMessageBox.critical(self, "处理失败", message)

        @Slot()
        def _reset_form(self) -> None:
            self.audio_path_edit.clear()
            self.bilingual_radio.setChecked(True)
            self.scene_combo.setCurrentText(SCENE_PRESETS[0])
            self.output_path_edit.clear()
            self.output_list.clear()
            self.preview_edit.clear()
            self.log_edit.clear()
            self.status_label.setText(READY_STATUS)
            self.startup_blocked = False
            self._show_startup_summary(build_startup_report(), startup=True)


    def main() -> None:
        app = QApplication(sys.argv)
        _apply_safe_qt_font_policy()
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
else:
    class TkMainWindow:
        def __init__(self) -> None:
            self.root = tk.Tk()
            self.root.title(f"{APP_TITLE} (Tkinter 回退模式)")
            self.root.geometry("1180x760")
            self.output_dir = AppConfig().output_dir
            self.event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
            self.worker_thread: threading.Thread | None = None
            self.startup_blocked = False
            self.audio_path_var = tk.StringVar()
            self.scene_var = tk.StringVar(value=SCENE_PRESETS[0])
            self.mode_var = tk.StringVar(value="bilingual")
            self.output_path_var = tk.StringVar()
            self.status_var = tk.StringVar(value=READY_STATUS)

            container = ttk.Frame(self.root, padding=18)
            container.pack(fill="both", expand=True)
            ttk.Label(container, text=APP_TITLE).pack(anchor="w")
            ttk.Label(container, text=APP_SUBTITLE).pack(anchor="w")
            ttk.Label(container, textvariable=self.status_var).pack(fill="x", pady=(0, 8))

            audio_row = ttk.Frame(container)
            audio_row.pack(fill="x")
            self.audio_entry = ttk.Entry(audio_row, textvariable=self.audio_path_var)
            self.audio_entry.pack(side="left", fill="x", expand=True)
            self.browse_button = ttk.Button(audio_row, text="浏览音频", command=self._browse_audio)
            self.browse_button.pack(side="left", padx=(8, 0))

            mode_row = ttk.Frame(container)
            mode_row.pack(fill="x", pady=(8, 0))
            for text, value in [("原文字幕", "original"), ("译文字幕", "translation"), ("双语字幕", "bilingual")]:
                ttk.Radiobutton(
                    mode_row,
                    text=text,
                    variable=self.mode_var,
                    value=value,
                    command=self._update_scene_enabled,
                ).pack(side="left", padx=(0, 12))

            self.scene_combo = ttk.Combobox(container, textvariable=self.scene_var, values=SCENE_PRESETS)
            self.scene_combo.pack(fill="x", pady=(8, 0))
            self.start_button = ttk.Button(container, text="开始生成", command=self._start_task)
            self.start_button.pack(fill="x", pady=(8, 8))
            self.output_entry = ttk.Entry(container, textvariable=self.output_path_var, state="readonly")
            self.output_entry.pack(fill="x")
            self.output_list = tk.Listbox(container, height=4)
            self.output_list.pack(fill="x", pady=(8, 0))
            self.output_list.bind("<Double-1>", self._open_selected_output)
            self.log_edit = ScrolledText(container, wrap="word", height=12)
            self.log_edit.pack(fill="both", expand=True, pady=(8, 0))
            self.preview_edit = ScrolledText(container, wrap="word", height=12)
            self.preview_edit.pack(fill="both", expand=True, pady=(8, 0))

            footer = ttk.Frame(container)
            footer.pack(anchor="e", pady=(8, 0))
            ttk.Button(footer, text="打开输出目录", command=lambda: open_path(self.output_dir)).pack(side="left", padx=(0, 8))
            ttk.Button(footer, text="重新开始", command=self._reset_form).pack(side="left", padx=(0, 8))
            ttk.Button(footer, text="退出", command=self._on_close).pack(side="left")

            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
            self.root.after(100, self._poll_events)
            self._update_scene_enabled()
            if GUI_IMPORT_ERROR is not None:
                self._append_log(f"PySide6 不可用，已自动回退到 Tkinter：{GUI_IMPORT_ERROR}")
            self._show_startup_summary(build_startup_report(), startup=True)

        def _current_mode(self) -> str:
            return self.mode_var.get()

        def _update_scene_enabled(self) -> None:
            self.scene_combo.configure(state="normal" if self._current_mode() in TRANSLATION_MODES else "disabled")

        def _append_log(self, message: str) -> None:
            self.status_var.set(message)
            self.log_edit.insert("end", f"{message}\n")
            self.log_edit.see("end")

        def _show_startup_summary(self, report, *, startup: bool) -> None:
            for line in format_startup_report(report):
                self._append_log(line)
            if report.has_fatal:
                if startup:
                    self.startup_blocked = True
                    self.start_button.configure(state="disabled")
                messagebox.showerror(
                    "启动自检未通过" if startup else "任务前检查未通过",
                    build_startup_report_message(report),
                )

        def _browse_audio(self) -> None:
            file_path = filedialog.askopenfilename(
                title="选择音频文件",
                initialdir=str(APP_ROOT),
                filetypes=[("音频文件", "*.mp3 *.wav *.m4a *.flac *.aac"), ("所有文件", "*.*")],
            )
            if file_path:
                self.audio_path_var.set(file_path)

        def _start_task(self) -> None:
            audio_path = self.audio_path_var.get().strip().strip('"').strip("'")
            subtitle_mode = self._current_mode()
            scene = self.scene_var.get().strip() if subtitle_mode in TRANSLATION_MODES else None
            try:
                validate_task_request(audio_path, subtitle_mode, scene)
            except Exception as exc:
                message, suggestion = build_gui_error_message(exc)
                messagebox.showerror("无法开始任务", message if not suggestion else f"{message}\n{suggestion}")
                return

            self.output_path_var.set("")
            self.output_list.delete(0, "end")
            self.log_edit.delete("1.0", "end")
            self.preview_edit.delete("1.0", "end")

            report = build_startup_report(subtitle_mode)
            self.startup_blocked = False
            self._show_startup_summary(report, startup=False)
            if report.has_fatal:
                return

            self.start_button.configure(state="disabled")
            self.worker_thread = threading.Thread(
                target=self._run_task,
                args=(audio_path, subtitle_mode, scene),
                daemon=True,
            )
            self.worker_thread.start()

        def _run_task(self, audio_path: str, subtitle_mode: str, scene: str | None) -> None:
            try:
                result = execute_gui_task(
                    audio_path,
                    subtitle_mode,
                    scene,
                    progress_callback=lambda message: self.event_queue.put(("progress", message)),
                )
                self.event_queue.put(("success", result))
            except BackendProcessError as exc:
                message, suggestion = parse_backend_error(exc.stderr_text)
                self.event_queue.put(("failure", message if not suggestion else f"{message}\n{suggestion}"))
            except Exception as exc:
                message, suggestion = build_gui_error_message(exc)
                self.event_queue.put(("failure", message if not suggestion else f"{message}\n{suggestion}"))

        def _poll_events(self) -> None:
            while True:
                try:
                    event_type, payload = self.event_queue.get_nowait()
                except queue.Empty:
                    break
                if event_type == "progress":
                    self._append_log(str(payload))
                elif event_type == "success":
                    self._handle_success(payload)  # type: ignore[arg-type]
                else:
                    self._handle_failure(str(payload))
            self.root.after(100, self._poll_events)

        def _handle_success(self, result: dict) -> None:
            output_file = Path(result["output_file"])
            self.output_path_var.set(str(output_file.resolve()))
            self.output_list.insert("end", output_file.name)
            if output_file.exists():
                self.preview_edit.delete("1.0", "end")
                self.preview_edit.insert("1.0", output_file.read_text(encoding="utf-8"))
            self._append_log("任务完成。")
            self.start_button.configure(state="normal")
            self.worker_thread = None

        def _handle_failure(self, message: str) -> None:
            self._append_log(message.replace("\n", " "))
            self.start_button.configure(state="normal")
            self.worker_thread = None
            messagebox.showerror("处理失败", message)

        def _reset_form(self) -> None:
            self.audio_path_var.set("")
            self.mode_var.set("bilingual")
            self.scene_var.set(SCENE_PRESETS[0])
            self.output_path_var.set("")
            self.output_list.delete(0, "end")
            self.log_edit.delete("1.0", "end")
            self.preview_edit.delete("1.0", "end")
            self.status_var.set(READY_STATUS)
            self.startup_blocked = False
            self._show_startup_summary(build_startup_report(), startup=True)

        def _open_selected_output(self, _event=None) -> None:
            selection = self.output_list.curselection()
            if selection:
                open_path(self.output_dir / self.output_list.get(selection[0]))

        def _on_close(self) -> None:
            if self.worker_thread and self.worker_thread.is_alive():
                messagebox.showinfo("任务进行中", "当前任务正在执行，请等待完成后再退出。")
                return
            self.root.destroy()

        def run(self) -> None:
            self.root.mainloop()


    MainWindow = TkMainWindow

    def main() -> None:
        TkMainWindow().run()


if __name__ == "__main__":
    main()
