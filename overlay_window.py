"""
Main overlay window for the Interview AI Agent.
Frameless, floating, semi-transparent, screen-capture resistant.
Features: live transcription, streamed AI responses, mic toggle,
session management, past chats sidebar, document uploads.
"""

import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTextEdit, QLabel, QSlider, QFileDialog, QInputDialog, QMessageBox,
    QListWidget, QListWidgetItem, QSplitter, QFrame, QMenu, QSizeGrip,
    QApplication,
)
from PyQt6.QtCore import Qt, QPoint, pyqtSlot, QSize, QTimer
from PyQt6.QtGui import QFont, QAction, QCursor, QColor, QTextCursor

from audio_manager import AudioManager
from transcriber import Transcriber
from llm_client import LLMClient
import context_manager
import storage_manager
import screen_reader


class OverlayWindow(QMainWindow):
    """The main stealth overlay widget."""

    def __init__(self):
        super().__init__()
        self._session_id = None
        self._drag_pos = None
        self._last_question = ""
        self._captured_text = ""      # accumulates across multiple captures
        self._append_mode = False      # when True, capture appends instead of replacing

        # Core components
        self.audio_mgr = AudioManager()
        self.transcriber = Transcriber()
        self.llm_client = LLMClient()

        self._setup_window()
        self._build_ui()
        self._connect_signals()

        # Load whisper model on start
        self.transcriber.load_model()
        self.llm_client.initialize()

    # ─── Window Configuration ────────────────────────────────

    def _setup_window(self):
        """Configure the window as a floating stealth overlay."""
        self.setWindowTitle("InterviewAgent")

        # Frameless, always-on-top, tool window (doesn't appear in dock/taskbar)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Default geometry
        from config import load_config
        cfg = load_config()
        self.setGeometry(
            cfg.get("window_x", 100),
            cfg.get("window_y", 100),
            cfg.get("window_width", 420),
            cfg.get("window_height", 620),
        )
        self.setMinimumSize(320, 400)

        # Set opacity
        self.setWindowOpacity(cfg.get("window_opacity", 0.92))

    def apply_stealth(self):
        """Apply macOS stealth settings via pyobjc."""
        try:
            from AppKit import NSApp
            from Cocoa import (
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorStationary,
                NSWindowCollectionBehaviorFullScreenAuxiliary,
            )

            ns_window = None
            for w in NSApp.windows():
                if "InterviewAgent" in str(w.title()):
                    ns_window = w
                    break

            if ns_window is None:
                # Try getting by window number
                win_id = int(self.winId())
                for w in NSApp.windows():
                    if w.windowNumber() == win_id:
                        ns_window = w
                        break

            if ns_window:
                # Make invisible to screen capture
                ns_window.setSharingType_(0)  # NSWindowSharingNone

                # Float above full-screen apps
                ns_window.setLevel_(3)  # NSFloatingWindowLevel

                # Visible on all spaces, over full-screen
                behavior = (
                    NSWindowCollectionBehaviorCanJoinAllSpaces
                    | NSWindowCollectionBehaviorStationary
                    | NSWindowCollectionBehaviorFullScreenAuxiliary
                )
                ns_window.setCollectionBehavior_(behavior)

                self.status_label.setText("🛡 Stealth active")
            else:
                self.status_label.setText("⚠ Could not find NSWindow")

        except ImportError:
            self.status_label.setText("⚠ pyobjc not available — no stealth")
        except Exception as e:
            self.status_label.setText(f"⚠ Stealth error: {str(e)[:40]}")

    # ─── UI Construction ─────────────────────────────────────

    def _build_ui(self):
        """Build the complete UI."""
        # Central widget with main layout
        central = QWidget()
        central.setObjectName("centralWidget")
        central.setStyleSheet("""
            #centralWidget {
                background-color: rgba(30, 30, 35, 240);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Title bar
        main_layout.addWidget(self._build_title_bar())

        # Content area with optional sidebar
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setStyleSheet("QSplitter::handle { background: rgba(255,255,255,0.1); }")

        # Sidebar (past chats) — hidden by default
        self.sidebar = self._build_sidebar()
        self.sidebar.setVisible(False)
        self.splitter.addWidget(self.sidebar)

        # Main content
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 8, 12, 12)
        content_layout.setSpacing(8)

        # Control buttons row
        content_layout.addWidget(self._build_controls())

        # Question display
        q_label = QLabel("INTERVIEWER'S QUESTION")
        q_label.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 10px; font-weight: bold; letter-spacing: 1px;")
        content_layout.addWidget(q_label)

        self.question_display = QTextEdit()
        self.question_display.setReadOnly(True)
        self.question_display.setMaximumHeight(100)
        self.question_display.setPlaceholderText("Waiting for interviewer to speak...")
        self.question_display.setStyleSheet("""
            QTextEdit {
                background-color: rgba(255, 255, 255, 0.06);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
            }
        """)
        content_layout.addWidget(self.question_display)

        # AI Response display
        r_label = QLabel("AI RESPONSE")
        r_label.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 10px; font-weight: bold; letter-spacing: 1px;")
        content_layout.addWidget(r_label)

        self.response_display = QTextEdit()
        self.response_display.setReadOnly(True)
        self.response_display.setPlaceholderText("AI response will appear here...")
        self.response_display.setStyleSheet("""
            QTextEdit {
                background-color: rgba(255, 255, 255, 0.06);
                color: #f0f0f0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
                selection-background-color: rgba(100, 100, 255, 0.3);
            }
        """)
        content_layout.addWidget(self.response_display, 1)

        # Bottom actions row
        content_layout.addWidget(self._build_bottom_bar())

        # Status bar
        self.status_label = QLabel("Initializing...")
        self.status_label.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 10px; padding: 2px 4px;")
        content_layout.addWidget(self.status_label)

        # Audio device label
        self.device_label = QLabel(f"Audio: {self.audio_mgr.get_device_name()}")
        self.device_label.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 9px; padding: 0 4px;")
        content_layout.addWidget(self.device_label)

        # Size grip for resizing
        grip_layout = QHBoxLayout()
        grip_layout.addStretch()
        self.size_grip = QSizeGrip(self)
        self.size_grip.setStyleSheet("QSizeGrip { width: 14px; height: 14px; }")
        grip_layout.addWidget(self.size_grip)
        content_layout.addLayout(grip_layout)

        self.splitter.addWidget(content)
        main_layout.addWidget(self.splitter)

    def _build_title_bar(self) -> QWidget:
        """Build custom draggable title bar."""
        bar = QWidget()
        bar.setFixedHeight(36)
        bar.setStyleSheet("""
            QWidget {
                background-color: rgba(40, 40, 48, 250);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 8, 0)

        title = QLabel("🤖 InterviewAgent")
        title.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 12px; font-weight: bold;")
        layout.addWidget(title)

        layout.addStretch()

        # Opacity slider
        opacity_icon = QLabel("◐")
        opacity_icon.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 12px;")
        layout.addWidget(opacity_icon)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(92)
        self.opacity_slider.setFixedWidth(60)
        self.opacity_slider.setStyleSheet("""
            QSlider::groove:horizontal { background: rgba(255,255,255,0.15); height: 3px; border-radius: 1px; }
            QSlider::handle:horizontal { background: #aaa; width: 10px; margin: -4px 0; border-radius: 5px; }
        """)
        self.opacity_slider.valueChanged.connect(
            lambda v: self.setWindowOpacity(v / 100.0)
        )
        layout.addWidget(self.opacity_slider)

        # Minimize button
        min_btn = QPushButton("—")
        min_btn.setFixedSize(24, 24)
        min_btn.setStyleSheet("""
            QPushButton { color: rgba(255,255,255,0.6); background: transparent; border: none; font-size: 14px; }
            QPushButton:hover { color: white; background: rgba(255,255,255,0.1); border-radius: 4px; }
        """)
        min_btn.clicked.connect(self.showMinimized)
        layout.addWidget(min_btn)

        # Close button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("""
            QPushButton { color: rgba(255,255,255,0.6); background: transparent; border: none; font-size: 12px; }
            QPushButton:hover { color: white; background: rgba(255,80,80,0.6); border-radius: 4px; }
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        return bar

    def _build_controls(self) -> QWidget:
        """Build the control buttons row."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        btn_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #d0d0d0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                color: white;
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.05);
            }
        """

        active_btn_style = """
            QPushButton {
                background-color: rgba(80, 200, 120, 0.25);
                color: #80c878;
                border: 1px solid rgba(80, 200, 120, 0.3);
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(80, 200, 120, 0.35);
                color: #a0e898;
            }
        """

        # Mic / capture toggle
        self.mic_btn = QPushButton("🎤 Start")
        self.mic_btn.setStyleSheet(btn_style)
        self.mic_btn.clicked.connect(self._toggle_capture)
        layout.addWidget(self.mic_btn)

        # Pause/Resume toggle
        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.setStyleSheet(btn_style)
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._toggle_pause)
        layout.addWidget(self.pause_btn)

        # Regenerate button
        self.regen_btn = QPushButton("🔄 Regen")
        self.regen_btn.setStyleSheet(btn_style)
        self.regen_btn.setEnabled(False)
        self.regen_btn.clicked.connect(self._regenerate)
        layout.addWidget(self.regen_btn)

        # Stop generation button
        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setStyleSheet(btn_style)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_generation)
        layout.addWidget(self.stop_btn)

        # Past chats sidebar toggle
        self.sidebar_btn = QPushButton("📂")
        self.sidebar_btn.setFixedSize(32, 32)
        self.sidebar_btn.setStyleSheet(btn_style)
        self.sidebar_btn.setToolTip("Past Chats")
        self.sidebar_btn.clicked.connect(self._toggle_sidebar)
        layout.addWidget(self.sidebar_btn)

        # ── Screen capture controls ──────────────────────────────
        # Visual separator
        sep = QLabel("│")
        sep.setStyleSheet("color: rgba(255,255,255,0.15); font-size: 16px; padding: 0 2px;")
        layout.addWidget(sep)

        # Capture button
        self.capture_btn = QPushButton("📷 Capture")
        self.capture_btn.setStyleSheet(btn_style)
        self.capture_btn.setToolTip("Capture text from screen (AX API / OCR)")
        self.capture_btn.clicked.connect(self._capture_screen)
        layout.addWidget(self.capture_btn)

        # Append mode toggle
        self.append_btn = QPushButton("➕")
        self.append_btn.setFixedSize(32, 32)
        self.append_btn.setCheckable(True)
        self.append_btn.setStyleSheet(btn_style)
        self.append_btn.setToolTip("Append mode: each capture adds to question (for scrollable content)")
        self.append_btn.clicked.connect(self._toggle_append_mode)
        layout.addWidget(self.append_btn)

        # Clear captured text
        self.clear_capture_btn = QPushButton("🗑")
        self.clear_capture_btn.setFixedSize(32, 32)
        self.clear_capture_btn.setStyleSheet(btn_style)
        self.clear_capture_btn.setToolTip("Clear captured question text")
        self.clear_capture_btn.clicked.connect(self._clear_capture)
        layout.addWidget(self.clear_capture_btn)

        return widget

    def _build_bottom_bar(self) -> QWidget:
        """Build bottom action bar with upload and session controls."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        small_btn_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.06);
                color: rgba(255, 255, 255, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
                color: white;
            }
        """

        # Upload resume
        resume_btn = QPushButton("📄 Resume")
        resume_btn.setStyleSheet(small_btn_style)
        resume_btn.clicked.connect(self._upload_resume)
        layout.addWidget(resume_btn)

        # Upload code
        code_btn = QPushButton("📁 Code")
        code_btn.setStyleSheet(small_btn_style)
        code_btn.clicked.connect(self._upload_code)
        layout.addWidget(code_btn)

        layout.addStretch()

        # Document count indicator
        docs = context_manager.get_all_documents()
        self.doc_label = QLabel(f"📌 {len(docs)} docs loaded")
        self.doc_label.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 10px;")
        layout.addWidget(self.doc_label)

        layout.addStretch()

        # New Session
        new_btn = QPushButton("▶ New Session")
        new_btn.setStyleSheet(small_btn_style)
        new_btn.clicked.connect(self._new_session)
        layout.addWidget(new_btn)

        # End Session
        end_btn = QPushButton("⏹ End Session")
        end_btn.setStyleSheet(small_btn_style)
        end_btn.clicked.connect(self._end_session)
        layout.addWidget(end_btn)

        return widget

    def _build_sidebar(self) -> QWidget:
        """Build the past chats sidebar."""
        sidebar = QWidget()
        sidebar.setFixedWidth(180)
        sidebar.setStyleSheet("""
            QWidget {
                background-color: rgba(25, 25, 30, 240);
                border-right: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        label = QLabel("PAST INTERVIEWS")
        label.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 10px; font-weight: bold; letter-spacing: 1px;")
        layout.addWidget(label)

        self.chat_list = QListWidget()
        self.chat_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                color: #c0c0c0;
                border: none;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: rgba(255, 255, 255, 0.08);
            }
            QListWidget::item:selected {
                background-color: rgba(100, 100, 255, 0.2);
                color: white;
            }
        """)
        self.chat_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_list.customContextMenuRequested.connect(self._chat_context_menu)
        self.chat_list.itemClicked.connect(self._view_past_chat)
        layout.addWidget(self.chat_list)

        self._refresh_chat_list()

        return sidebar

    # ─── Signal Connections ───────────────────────────────────

    def _connect_signals(self):
        """Wire up all signals between components."""
        # Audio → Transcriber
        self.audio_mgr.audio_chunk_ready.connect(self.transcriber.transcribe)
        self.audio_mgr.status_changed.connect(self._update_audio_status)

        # Transcriber → UI + LLM
        self.transcriber.transcription_ready.connect(self._on_transcription)
        self.transcriber.status_changed.connect(self._update_status)

        # LLM → UI
        self.llm_client.token_received.connect(self._on_token)
        self.llm_client.response_complete.connect(self._on_response_complete)
        self.llm_client.generation_started.connect(self._on_generation_started)
        self.llm_client.status_changed.connect(self._update_status)

    # ─── Slots / Handlers ────────────────────────────────────

    @pyqtSlot(str)
    def _on_transcription(self, text: str):
        """Handle transcribed text — display and auto-trigger LLM."""
        self._last_question = text
        self.question_display.setPlainText(text)
        self.regen_btn.setEnabled(True)

        # Auto-save question if session active
        if self._session_id:
            storage_manager.add_message(self._session_id, "question", text)

        # Auto-trigger LLM response
        self.response_display.clear()
        self.llm_client.generate_response(text)

    @pyqtSlot(str)
    def _on_token(self, token: str):
        """Append streamed token to response display."""
        cursor = self.response_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(token)
        self.response_display.setTextCursor(cursor)
        self.response_display.ensureCursorVisible()
        self.stop_btn.setEnabled(True)

    @pyqtSlot()
    def _on_generation_started(self):
        """Handle generation start."""
        self.stop_btn.setEnabled(True)
        self.regen_btn.setEnabled(False)

    @pyqtSlot(str)
    def _on_response_complete(self, response: str):
        """Handle completed response."""
        self.stop_btn.setEnabled(False)
        self.regen_btn.setEnabled(True)

        # Auto-save answer if session active
        if self._session_id and response:
            storage_manager.add_message(self._session_id, "answer", response)

    @pyqtSlot(str)
    def _update_status(self, status: str):
        """Update the status label."""
        self.status_label.setText(status)

    @pyqtSlot(str)
    def _update_audio_status(self, status: str):
        """Update both status and device labels."""
        self.status_label.setText(status)
        self.device_label.setText(f"Audio: {self.audio_mgr.get_device_name()}")

    # ─── Button Actions ──────────────────────────────────────

    def _toggle_capture(self):
        """Start/stop audio capture."""
        if self.audio_mgr.is_capturing:
            self.audio_mgr.stop_capture()
            # Read actual state after the call
            self.mic_btn.setText("🎤 Start")
            self.pause_btn.setEnabled(False)
        else:
            success = self.audio_mgr.start_capture()
            # Only update UI if capture actually started
            if success:
                self.mic_btn.setText("🎤 Stop")
                self.pause_btn.setEnabled(True)
            # If failed, status_changed signal already updated the status label

    def _toggle_pause(self):
        """Pause/resume audio capture."""
        self.audio_mgr.toggle_pause()
        if self.audio_mgr.is_paused:
            self.pause_btn.setText("▶ Resume")
        else:
            self.pause_btn.setText("⏸ Pause")

    def _regenerate(self):
        """Regenerate response for the last question."""
        if self._last_question:
            self.response_display.clear()
            self.llm_client.generate_response(self._last_question)

    def _stop_generation(self):
        """Stop current LLM generation."""
        self.llm_client.stop_generation()
        self.stop_btn.setEnabled(False)
        self.regen_btn.setEnabled(True)

    # ─── Screen Capture ──────────────────────────────────────

    def _capture_screen(self):
        """
        Capture text from the screen using AX API or screenshot+OCR.
        Briefly hides our overlay so it doesn't occlude content.
        """
        self.capture_btn.setEnabled(False)
        self.capture_btn.setText("⏳ Capturing...")
        self.status_label.setText("Capturing screen...")

        # Hide window briefly to avoid occluding the target window
        self.hide()
        QApplication.processEvents()  # Flush the hide before scheduling capture
        QTimer.singleShot(150, self._finish_capture_screen)

    def _finish_capture_screen(self):
        """Run screen capture after the overlay has had time to hide."""
        result = {"text": "", "method": "error", "error": "Capture failed unexpectedly."}
        try:
            result = screen_reader.capture_text_from_screen()
        finally:
            self.show()
            self.raise_()
            self.capture_btn.setEnabled(True)
            self.capture_btn.setText("📷 Capture")

        text = result.get("text", "").strip()
        method = result.get("method", "error")
        error = result.get("error", "")

        if not text:
            self.status_label.setText(f"⚠ Capture failed: {error or 'No text found'}")
            return

        # Append or replace
        if self._append_mode and self._captured_text:
            self._captured_text += "\n\n--- [next scroll] ---\n\n" + text
        else:
            self._captured_text = text

        method_icon = "🔍" if method == "accessibility" else "📸"
        self.status_label.setText(
            f"{method_icon} Captured via {method} · {len(self._captured_text)} chars"
        )

        # Display in question box
        self.question_display.setPlainText(self._captured_text)
        self._last_question = self._captured_text
        self.regen_btn.setEnabled(True)

        # Auto-save to session
        if self._session_id:
            storage_manager.add_message(self._session_id, "question", self._captured_text)

        # Auto-trigger LLM response
        self.response_display.clear()
        self.llm_client.generate_response(self._captured_text)

    def _toggle_append_mode(self):
        """Toggle scroll-and-append capture mode."""
        self._append_mode = self.append_btn.isChecked()
        if self._append_mode:
            self.append_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 200, 60, 0.3);
                    color: #ffd060;
                    border: 1px solid rgba(255, 200, 60, 0.4);
                    border-radius: 6px;
                    font-size: 11px; font-weight: bold;
                }
            """)
            self.status_label.setText("➕ Append mode ON — captures will accumulate")
        else:
            self.append_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.08);
                    color: #d0d0d0;
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 6px;
                    font-size: 11px; font-weight: bold;
                }
            """)
            self.status_label.setText("Append mode OFF")

    def _clear_capture(self):
        """Clear accumulated captured text."""
        self._captured_text = ""
        self._last_question = ""
        self.question_display.clear()
        self.status_label.setText("🗑 Capture cleared")

    def _toggle_sidebar(self):
        """Toggle past chats sidebar visibility."""
        self.sidebar.setVisible(not self.sidebar.isVisible())
        if self.sidebar.isVisible():
            self._refresh_chat_list()

    def _upload_resume(self):
        """Upload a resume file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Upload Resume", "",
            "Resumes (*.pdf *.docx *.txt *.md)",
        )
        if filepath:
            doc = context_manager.add_resume(filepath)
            if doc.get("type") == "error":
                QMessageBox.warning(self, "Upload Error", doc.get("error", "Unknown error"))
                return
            self._update_doc_count()
            self.status_label.setText(f"✅ Loaded resume: {doc['filename']}")

    def _upload_code(self):
        """Upload a code file or folder."""
        # Show choice dialog
        msg = QMessageBox(self)
        msg.setWindowTitle("Upload Code")
        msg.setText("Upload a single file or entire project folder?")
        msg.setStyleSheet("""
            QMessageBox { background-color: #222; }
            QLabel { color: white; }
            QPushButton { background: #333; color: white; padding: 6px 16px; border-radius: 4px; }
            QPushButton:hover { background: #444; }
        """)
        file_btn = msg.addButton("Single File", QMessageBox.ButtonRole.AcceptRole)
        folder_btn = msg.addButton("Project Folder", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        if msg.clickedButton() == file_btn:
            filepath, _ = QFileDialog.getOpenFileName(
                self, "Upload Code File", "",
                "Source Code (*.py *.js *.ts *.jsx *.tsx *.java *.cpp *.c *.h *.go *.rs *.rb *.php *.swift *.kt *.scala *.sol *.css *.html *.sql *.sh *.yml *.yaml *.toml *.md *.txt *.cfg *.ini *.xml)"
            )
            if filepath:
                doc = context_manager.add_code_file(filepath)
                if doc.get("type") == "error":
                    QMessageBox.warning(self, "Upload Error", doc.get("error", "Unknown error"))
                    return
                self._update_doc_count()
                self.status_label.setText(f"✅ Loaded: {doc['filename']}")

        elif msg.clickedButton() == folder_btn:
            folder = QFileDialog.getExistingDirectory(self, "Select Project Folder")
            if folder:
                doc = context_manager.add_project_folder(folder)
                if doc.get("type") == "error":
                    QMessageBox.warning(self, "Upload Error", doc.get("error", "Unknown error"))
                    return
                self._update_doc_count()
                self.status_label.setText(
                    f"✅ Loaded project: {doc['filename']} ({doc['files_count']} files)"
                )

    def _update_doc_count(self):
        """Update the document count label."""
        docs = context_manager.get_all_documents()
        self.doc_label.setText(f"📌 {len(docs)} docs loaded")

    def _new_session(self):
        """Start a new interview session."""
        # End current session if active
        if self._session_id:
            self._end_session()

        self._session_id = storage_manager.start_session()
        self.llm_client.clear_history()
        self.question_display.clear()
        self.response_display.clear()
        self._last_question = ""
        self.status_label.setText(f"▶ Session started (#{self._session_id})")

        # Auto-start capture
        if not self.audio_mgr.is_capturing:
            self._toggle_capture()

    def _end_session(self):
        """End the current session with naming dialog."""
        if not self._session_id:
            self.status_label.setText("⚠ No active session")
            return

        # Stop capture
        if self.audio_mgr.is_capturing:
            self.audio_mgr.stop_capture()
            self.mic_btn.setText("🎤 Start")
            self.pause_btn.setEnabled(False)

        # Ask for session name
        name, ok = QInputDialog.getText(
            self,
            "Name This Interview",
            "Enter the company/interview name:",
            text="",
        )

        if ok and name.strip():
            storage_manager.end_session(self._session_id, name.strip())
        else:
            storage_manager.end_session(self._session_id)

        self.status_label.setText(f"✅ Session saved: {name if ok and name else 'Unnamed'}")
        self._session_id = None
        self._refresh_chat_list()

    # ─── Sidebar / Past Chats ────────────────────────────────

    def _refresh_chat_list(self):
        """Reload the past chats list."""
        self.chat_list.clear()
        sessions = storage_manager.get_all_sessions()
        for s in sessions:
            item = QListWidgetItem(f"{s['name']}")
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            item.setToolTip(f"Created: {s['created_at'][:16]}")
            self.chat_list.addItem(item)

    def _view_past_chat(self, item: QListWidgetItem):
        """View a past chat's conversation."""
        session_id = item.data(Qt.ItemDataRole.UserRole)
        messages = storage_manager.get_session_messages(session_id)

        self.question_display.clear()
        self.response_display.clear()

        display_text = ""
        for msg in messages:
            role = "❓ Q" if msg["role"] == "question" else "💡 A"
            display_text += f"{role}: {msg['content']}\n\n"

        self.response_display.setPlainText(display_text.strip())
        self.status_label.setText(f"Viewing: {item.text()}")

    def _chat_context_menu(self, pos):
        """Show right-click menu for chat items."""
        item = self.chat_list.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a2f;
                color: white;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item { padding: 6px 20px; border-radius: 3px; }
            QMenu::item:selected { background-color: rgba(100,100,255,0.3); }
        """)

        rename_action = menu.addAction("✏️ Rename")
        delete_action = menu.addAction("🗑 Delete")

        action = menu.exec(self.chat_list.mapToGlobal(pos))

        session_id = item.data(Qt.ItemDataRole.UserRole)

        if action == rename_action:
            new_name, ok = QInputDialog.getText(
                self, "Rename Session", "New name:", text=item.text()
            )
            if ok and new_name.strip():
                storage_manager.rename_session(session_id, new_name.strip())
                self._refresh_chat_list()

        elif action == delete_action:
            reply = QMessageBox.question(
                self, "Delete Session",
                f"Delete '{item.text()}'? This cannot be undone.",
            )
            if reply == QMessageBox.StandardButton.Yes:
                storage_manager.delete_session(session_id)
                self._refresh_chat_list()

    # ─── Window Dragging ─────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Only drag from title bar area (top 36px)
            if event.position().y() < 36:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def closeEvent(self, event):
        """Qt close event — catches Cmd+Q, window manager close, etc."""
        if self._on_close():
            event.accept()
        else:
            event.ignore()

    def _on_close(self) -> bool:
        """
        Handle close with session save prompt.
        Returns True if close should proceed, False if cancelled.
        """
        if self._session_id:
            reply = QMessageBox.question(
                self, "Active Session",
                "You have an active session. Save it before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._end_session()
            elif reply == QMessageBox.StandardButton.Cancel:
                return False

        # Save window position
        from config import load_config, save_config
        cfg = load_config()
        geo = self.geometry()
        cfg["window_x"] = geo.x()
        cfg["window_y"] = geo.y()
        cfg["window_width"] = geo.width()
        cfg["window_height"] = geo.height()
        cfg["window_opacity"] = self.windowOpacity()
        save_config(cfg)

        # Cleanup
        self.audio_mgr.stop_capture()
        return True
