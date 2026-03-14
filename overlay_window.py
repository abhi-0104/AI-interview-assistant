"""
Main overlay window. 
Frameless, floating, semi-transparent, screen-capture resistant.
Final version with Modern Chat UI, interactive prompt, and context-aware flow.
"""

import sys
import hashlib
import time
import datetime
from ctypes import c_void_p
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTextEdit, QLabel, QSlider, QFileDialog, QInputDialog, QMessageBox,
    QListWidget, QListWidgetItem, QSplitter, QFrame, QMenu, QSizeGrip,
    QApplication, QGraphicsDropShadowEffect, QTextBrowser, QLineEdit
)
from PyQt6.QtCore import Qt, QPoint, pyqtSlot, QSize, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QAction, QCursor, QColor, QTextCursor, QIcon

from audio_manager import AudioManager
from transcriber import Transcriber
from llm_client import LLMClient
import context_manager
import storage_manager
import screen_reader
from config import load_config, save_config


class OverlayWindow(QMainWindow):
    """The main stealth overlay widget - Modern Chat UI Build."""

    def __init__(self):
        super().__init__()
        self._session_id = None
        self._drag_pos = None
        self._resize_edge = None
        self._is_resizing = False
        self._last_hash = ""
        self._ns_window = None
        self._is_expanded = False
        self._start_time = None
        self._chat_html = "" # Store chat history for HTML rendering

        self.config = load_config()
        self.mode = self.config.get("app_mode", "interview")

        print(f"[UI] Initializing Chat-Enabled Overlay (Mode: {self.mode})")

        # Core components
        self.audio_mgr = AudioManager()
        self.transcriber = Transcriber()
        self.llm_client = LLMClient()

        self._setup_window()
        self._setup_tray()
        self._build_ui()
        self._connect_signals()

        # Passive polling timer
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self._run_passive_check)

        # Level enforcer
        self._level_timer = QTimer(self)
        self._level_timer.timeout.connect(self._enforce_level)
        self._level_timer.start(1000)

        # Live Timer for Toolbar
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)

        if self.mode == "interview":
            self.transcriber.load_model()
        else:
            self.auto_timer.start(3000)

        self.llm_client.initialize()
        self._new_session()

    def _setup_window(self):
        self.setWindowTitle("System Service")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self.toolbar_width = self.config.get("window_width", 750)
        self.toolbar_height = 48
        self.expanded_height = self.config.get("window_height", 550)

        self.setGeometry(
            self.config.get("window_x", 100),
            self.config.get("window_y", 100),
            self.toolbar_width,
            self.toolbar_height
        )
        self.setMinimumWidth(400)
        self.setMinimumHeight(self.toolbar_height)
        self.setWindowOpacity(self.config.get("window_opacity", 0.95))

    def _setup_tray(self):
        from PyQt6.QtWidgets import QSystemTrayIcon
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(
            self.style().StandardPixmap.SP_ComputerIcon
        ))
        tray_menu = QMenu()
        show_action = tray_menu.addAction("⚙ Restore & Capture")
        show_action.triggered.connect(self._restore_and_capture)
        exit_action = tray_menu.addAction("✕ Exit")
        exit_action.triggered.connect(QApplication.instance().quit)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_click)
        self.tray_icon.show()

    def _on_tray_click(self, reason):
        from PyQt6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._restore_and_capture()

    @pyqtSlot()
    def _restore_and_capture(self):
        print("[UI] Restore & Capture triggered.")
        self.status_label.setText("⌛ Capturing...")
        QApplication.processEvents()
        result = screen_reader.capture_text_from_screen(ax_only=False)
        text = result.get("text", "").strip()
        method = result.get("method", "unknown")
        error = result.get("error")
        
        try:
            from AppKit import NSApp
            NSApp().activateIgnoringOtherApps_(True)
        except Exception: pass
            
        self.show()
        self.raise_()
        self._enforce_level()
        if text:
            self._on_context_change(text, is_capture=True)
            self.status_label.setText(f"🎯 Captured via {method}")
        else:
            msg = f"⚠ {error}" if error else "⚠ Capture failed"
            self.status_label.setText(msg)

    def _update_clock(self):
        if self._start_time:
            elapsed = datetime.datetime.now() - self._start_time
            seconds = int(elapsed.total_seconds())
            mins, secs = divmod(seconds, 60)
            self.timer_label.setText(f"■ {mins:02}:{secs:02}")

    def _enforce_level(self):
        ns_window = self._find_ns_window()
        if ns_window:
            try:
                ns_window.setLevel_(1000)
                ns_window.orderFrontRegardless()
            except Exception: pass

    def _find_ns_window(self):
        if self._ns_window: return self._ns_window
        try:
            import objc
            ptr = int(self.winId())
            ns_view = objc.objc_object(c_void_p=ptr)
            ns_window = ns_view.window()
            if ns_window:
                self._ns_window = ns_window
                return ns_window
        except Exception: pass
        return None

    def apply_stealth(self):
        print("[UI] Applying Native Stealth Settings...")
        try:
            from Cocoa import (
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorStationary,
                NSWindowCollectionBehaviorFullScreenAuxiliary,
                NSWindowCollectionBehaviorIgnoresCycle,
            )
            ns_window = self._find_ns_window()
            if ns_window:
                ns_window.setSharingType_(0)
                if hasattr(ns_window, 'setExcludedFromCapture_'):
                    ns_window.setExcludedFromCapture_(True)
                ns_window.setLevel_(1000)
                ns_window.setCollectionBehavior_(
                    NSWindowCollectionBehaviorCanJoinAllSpaces |
                    NSWindowCollectionBehaviorStationary |
                    NSWindowCollectionBehaviorFullScreenAuxiliary |
                    NSWindowCollectionBehaviorIgnoresCycle
                )
                self.status_label.setText("🛡 Stealth Active")
        except Exception: pass

    def _build_ui(self):
        """Build the new Chat UI with a scrolling area and prompt box."""
        self.main_container = QWidget()
        self.main_container.setObjectName("mainContainer")
        self.main_container.setStyleSheet("""
            #mainContainer {
                background-color: rgba(20, 20, 25, 235);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        self.setCentralWidget(self.main_container)

        self.root_layout = QHBoxLayout(self.main_container)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        # 1. HISTORY PANEL
        self.history_panel = QWidget()
        self.history_panel.setFixedWidth(200)
        self.history_panel.setVisible(False)
        self.history_panel.setStyleSheet("background-color: rgba(15, 15, 20, 250); border-right: 1px solid rgba(255,255,255,0.05);")
        h_layout = QVBoxLayout(self.history_panel)
        h_title = QLabel("PAST SESSIONS")
        h_title.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 9px; font-weight: bold; margin-bottom: 5px;")
        h_layout.addWidget(h_title)
        self.chat_list = QListWidget()
        self.chat_list.setStyleSheet("background: transparent; border: none; color: #aaa; font-size: 11px;")
        h_layout.addWidget(self.chat_list)
        self.root_layout.addWidget(self.history_panel)

        # 2. MAIN CONTENT
        self.content_container = QWidget()
        self.layout = QVBoxLayout(self.content_container)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.root_layout.addWidget(self.content_container)

        self.toolbar = QWidget()
        self.toolbar.setFixedHeight(self.toolbar_height)
        self.toolbar_layout = QHBoxLayout(self.toolbar)
        self.toolbar_layout.setContentsMargins(12, 0, 12, 0)
        self.toolbar_layout.setSpacing(8)

        self.drag_handle = QLabel("✥")
        self.drag_handle.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 18px;")
        self.toolbar_layout.addWidget(self.drag_handle)

        self.logo_label = QLabel("🦜 Parakeet")
        self.logo_label.setStyleSheet("color: #00ff88; font-weight: bold; font-size: 13px;")
        self.toolbar_layout.addWidget(self.logo_label)

        btn_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08); color: white; border-radius: 6px;
                padding: 4px 10px; font-size: 11px; border: 1px solid rgba(255, 255, 255, 0.05);
            }
            QPushButton:hover { background-color: rgba(0, 255, 136, 0.15); border: 1px solid #00ff88; }
        """
        self.help_btn = QPushButton("AI Help ✨")
        self.help_btn.setStyleSheet(btn_style)
        self.help_btn.clicked.connect(self._restore_and_capture)
        self.toolbar_layout.addWidget(self.help_btn)

        self.analyze_btn = QPushButton("Analyze 🖥")
        self.analyze_btn.setStyleSheet(btn_style)
        self.analyze_btn.clicked.connect(self._capture_screen)
        self.toolbar_layout.addWidget(self.analyze_btn)

        self.chat_btn = QPushButton("Chat 💬")
        self.chat_btn.setStyleSheet(btn_style)
        self.chat_btn.clicked.connect(self._toggle_history)
        self.toolbar_layout.addWidget(self.chat_btn)

        self.toolbar_layout.addStretch()

        self.timer_label = QLabel("■ 00:00")
        self.timer_label.setStyleSheet("background: rgba(40,40,45,255); color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-family: 'Menlo', monospace;")
        self.toolbar_layout.addWidget(self.timer_label)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 9px;")
        self.toolbar_layout.addWidget(self.status_label)

        self.expand_btn = QPushButton("▼")
        self.expand_btn.setFixedSize(30, 26)
        self.expand_btn.setStyleSheet("background: rgba(255,255,255,0.1); color: white; border-radius: 4px;")
        self.expand_btn.clicked.connect(self._toggle_expand)
        self.toolbar_layout.addWidget(self.expand_btn)

        self.settings_btn = QPushButton("⋮")
        self.settings_btn.setFixedSize(24, 24)
        self.settings_btn.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 18px; border: none; background: transparent;")
        self.settings_btn.clicked.connect(self._show_settings_menu)
        self.toolbar_layout.addWidget(self.settings_btn)

        self.layout.addWidget(self.toolbar)

        # CHAT AREA
        self.content_pane = QWidget()
        self.content_pane.setVisible(False)
        self.pane_layout = QVBoxLayout(self.content_pane)
        self.pane_layout.setContentsMargins(10, 0, 10, 10)
        self.pane_layout.setSpacing(10)

        # Scrolling Chat View
        self.chat_view = QTextBrowser()
        self.chat_view.setOpenExternalLinks(True)
        self.chat_view.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
                color: #e0e0e0;
                font-size: 12px;
                line-height: 1.6;
            }
        """)
        self.pane_layout.addWidget(self.chat_view, 1)

        # Follow-up Input Box
        self.input_container = QFrame()
        self.input_container.setStyleSheet("background-color: rgba(255,255,255,0.05); border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);")
        self.input_layout = QHBoxLayout(self.input_container)
        self.input_layout.setContentsMargins(8, 5, 8, 5)

        self.prompt_box = QLineEdit()
        self.prompt_box.setPlaceholderText("Ask a follow-up or type a command...")
        self.prompt_box.setStyleSheet("background: transparent; border: none; color: white; font-size: 12px; padding: 5px;")
        self.prompt_box.returnPressed.connect(self._send_follow_up)
        self.input_layout.addWidget(self.prompt_box)

        self.send_btn = QPushButton("➜")
        self.send_btn.setFixedSize(28, 28)
        self.send_btn.setStyleSheet("background: #00ff88; color: #111; border-radius: 14px; font-weight: bold; font-size: 14px;")
        self.send_btn.clicked.connect(self._send_follow_up)
        self.input_layout.addWidget(self.send_btn)

        self.pane_layout.addWidget(self.input_container)
        self.layout.addWidget(self.content_pane)

    def _toggle_history(self):
        self.history_panel.setVisible(not self.history_panel.isVisible())
        if self.history_panel.isVisible():
            self._refresh_history_list()
        
    def _refresh_history_list(self):
        self.chat_list.clear()
        for session in storage_manager.get_all_sessions():
            item = QListWidgetItem(session["name"])
            item.setData(Qt.ItemDataRole.UserRole, session["id"])
            self.chat_list.addItem(item)

    def _toggle_expand(self):
        self._is_expanded = not self._is_expanded
        target_height = self.expanded_height if self._is_expanded else self.toolbar_height
        self.setFixedHeight(target_height)
        self.content_pane.setVisible(self._is_expanded)
        self.expand_btn.setText("▲" if self._is_expanded else "▼")

    def _show_settings_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("background: #1a1a20; color: white;")
        
        audio_menu = menu.addMenu("🎤 Select Audio Input")
        for dev in self.audio_mgr.get_available_devices():
            act = audio_menu.addAction(dev["name"])
            act.triggered.connect(lambda _, idx=dev["index"]: self.audio_mgr.set_device(idx))

        model_menu = menu.addMenu("🤖 Switch AI Model")
        models = [
            ("Qwen 3 (Free/Legacy)", "qwen/qwen3-coder:free"),
            ("Gemini 2.0 Flash (Reliable)", "google/gemini-2.0-flash-001"),
            ("GPT-4o Mini (Fast)", "openai/gpt-4o-mini"),
            ("Claude 3.5 Sonnet (Advanced)", "anthropic/claude-3.5-sonnet"),
        ]
        curr_model = self.config.get("openrouter_model")
        for label, m_id in models:
            is_curr = (m_id == curr_model)
            act = model_menu.addAction(f"{'● ' if is_curr else '  '}{label}")
            act.triggered.connect(lambda _, m=m_id: self._set_ai_model(m))

        mode_act = menu.addAction(f"Switch to {'Assessment' if self.mode == 'interview' else 'Interview'}")
        mode_act.triggered.connect(self._toggle_mode)
        
        menu.addSeparator()
        up_act = menu.addAction("📄 Load Document")
        up_act.triggered.connect(self._upload_resume)
        
        exit_act = menu.addAction("✕ Exit")
        exit_act.triggered.connect(QApplication.instance().quit)
        menu.exec(QCursor.pos())

    def _set_ai_model(self, model_id):
        self.config["openrouter_model"] = model_id
        save_config(self.config)
        self.llm_client.config["openrouter_model"] = model_id
        self.status_label.setText(f"AI: {model_id.split('/')[-1]}")

    def _toggle_mode(self):
        self.mode = "assessment" if self.mode == "interview" else "interview"
        self.config["app_mode"] = self.mode
        save_config(self.config)
        self.status_label.setText(f"Mode: {self.mode.capitalize()}")
        if self.mode == "assessment":
            self.audio_mgr.stop_capture()
            self.auto_timer.start(3000)
        else:
            self.auto_timer.stop()
            self.transcriber.load_model()

    def _run_passive_check(self):
        result = screen_reader.capture_text_from_screen(ax_only=True)
        text = result.get("text", "").strip()
        if not text: return
        current_hash = hashlib.md5(text.encode()).hexdigest()
        if current_hash != self._last_hash:
            print("[UI] Passive check content detected.")
            self._last_hash = current_hash
            self._on_context_change(text, is_capture=True)

    def _append_to_chat(self, text, role="ai"):
        """Append a message bubble to the chat display."""
        if role == "user":
            bubble = f"""
            <div style="margin-top: 10px; margin-bottom: 5px;">
                <span style="color: #888; font-size: 10px; font-weight: bold;">USER / SCREEN</span><br>
                <div style="background-color: rgba(255,255,255,0.06); border-radius: 8px; padding: 10px; color: #ccc;">
                    {text.replace('\n', '<br>')}
                </div>
            </div>
            """
        else:
            bubble = f"""
            <div style="margin-top: 10px; margin-bottom: 5px;">
                <span style="color: #00ff88; font-size: 10px; font-weight: bold;">PARAKEET AI</span><br>
                <div id="latest-ai-reply" style="color: #eee; padding: 5px 0;">
                    {text}
                </div>
            </div>
            """
        self._chat_html += bubble
        self.chat_view.setHtml(self._chat_html)
        self.chat_view.verticalScrollBar().setValue(self.chat_view.verticalScrollBar().maximum())

    def _on_context_change(self, text, is_capture=False):
        print(f"[UI] Processing message. Expand: {not self._is_expanded}")
        if not self._is_expanded:
            self._toggle_expand()
        
        display_text = f"📷 Screen Capture ({len(text)} chars)" if is_capture else text
        self._append_to_chat(display_text, role="user")
        
        # Start AI response
        self._current_ai_text = ""
        self._chat_html += f"""
            <div style="margin-top: 10px; margin-bottom: 5px;">
                <span style="color: #00ff88; font-size: 10px; font-weight: bold;">PARAKEET AI</span><br>
                <div id="streaming-node" style="color: #eee; padding: 5px 0;">
        """
        self.llm_client.generate_response(text)

    def _send_follow_up(self):
        text = self.prompt_box.text().strip()
        if not text: return
        self.prompt_box.clear()
        self._on_context_change(text, is_capture=False)

    def _connect_signals(self):
        self.audio_mgr.audio_chunk_ready.connect(self.transcriber.transcribe)
        self.transcriber.transcription_ready.connect(self._on_transcription)
        self.llm_client.token_received.connect(self._on_token)
        self.llm_client.response_complete.connect(self._on_response_complete)
        self.llm_client.status_changed.connect(lambda s: self.status_label.setText(s))
        self.audio_mgr.status_changed.connect(lambda s: self.status_label.setText(s))

    @pyqtSlot(str)
    def _on_token(self, token):
        self._current_ai_text += token
        # Dynamic streaming update to HTML
        # We replace the closing tags of the last bubble for a seamless stream feel
        temp_html = self._chat_html + self._current_ai_text.replace('\n', '<br>') + "</div></div>"
        self.chat_view.setHtml(temp_html)
        self.chat_view.verticalScrollBar().setValue(self.chat_view.verticalScrollBar().maximum())

    @pyqtSlot(str)
    def _on_response_complete(self, full_text):
        # Permanently commit the full response to chat buffer
        self._chat_html += full_text.replace('\n', '<br>') + "</div></div>"
        self.chat_view.setHtml(self._chat_html)
        self.chat_view.verticalScrollBar().setValue(self.chat_view.verticalScrollBar().maximum())

    def _capture_screen(self):
        self.status_label.setText("⌛ Analyzing...")
        QApplication.processEvents()
        exclude = None
        if self._ns_window:
            try: exclude = self._ns_window.windowNumber()
            except: pass
        result = screen_reader.capture_text_from_screen(exclude_id=exclude)
        text = result.get("text", "").strip()
        if text:
            self._on_context_change(text, is_capture=True)
        else:
            self.status_label.setText(f"⚠ {result.get('error','Empty')}")

    @pyqtSlot(str)
    def _on_transcription(self, text):
        self._on_context_change(text, is_capture=False)

    def _new_session(self):
        self._session_id = storage_manager.start_session()
        self._start_time = datetime.datetime.now()
        self.clock_timer.start(1000)
        self.llm_client.clear_history()
        self._chat_html = ""
        self.chat_view.clear()
        self._append_to_chat("👋 Hello! I'm ready to help. Capture your screen or type a message.", role="ai")

    def _upload_resume(self):
        ns_window = self._find_ns_window()
        if ns_window: ns_window.setLevel_(0)
        path, _ = QFileDialog.getOpenFileName(self, "Load Document", "", "Docs (*.pdf *.docx *.txt)")
        if ns_window:
            ns_window.setLevel_(1000)
            ns_window.orderFrontRegardless()
        if path:
            context_manager.add_resume(path)
            self.status_label.setText("📄 Doc Loaded")

    def _get_resize_edge(self, pos: QPoint):
        margin = 8
        rect = self.rect()
        edge = 0
        if pos.x() < margin: edge |= Qt.Edge.LeftEdge.value
        if pos.x() > rect.width() - margin: edge |= Qt.Edge.RightEdge.value
        if pos.y() < margin: edge |= Qt.Edge.TopEdge.value
        if pos.y() > rect.height() - margin: edge |= Qt.Edge.BottomEdge.value
        return edge if edge != 0 else None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._get_resize_edge(event.position().toPoint())
            if edge:
                self._is_resizing = True
                self._resize_edge = edge
                event.accept()
            elif event.position().y() < self.toolbar_height:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        try:
            pos = event.position().toPoint()
            if not self._is_resizing:
                edge = self._get_resize_edge(pos)
                if edge is not None and edge != 0:
                    ev = edge
                    if ev & (Qt.Edge.LeftEdge.value | Qt.Edge.RightEdge.value) and ev & (Qt.Edge.TopEdge.value | Qt.Edge.BottomEdge.value):
                        self.setCursor(Qt.CursorShape.SizeFDiagCursor if (ev & Qt.Edge.LeftEdge.value) == (ev & Qt.Edge.TopEdge.value) else Qt.CursorShape.SizeBDiagCursor)
                    elif ev & (Qt.Edge.LeftEdge.value | Qt.Edge.RightEdge.value): self.setCursor(Qt.CursorShape.SizeHorCursor)
                    elif ev & (Qt.Edge.TopEdge.value | Qt.Edge.BottomEdge.value): self.setCursor(Qt.CursorShape.SizeVerCursor)
                    else: self.setCursor(Qt.CursorShape.ArrowCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)

            if self._is_resizing:
                rect = self.geometry()
                global_pos = event.globalPosition().toPoint()
                if self._resize_edge & Qt.Edge.LeftEdge.value: rect.setLeft(min(global_pos.x(), rect.right() - self.minimumWidth()))
                if self._resize_edge & Qt.Edge.RightEdge.value: rect.setRight(global_pos.x())
                if self._resize_edge & Qt.Edge.TopEdge.value: rect.setTop(min(global_pos.y(), rect.bottom() - self.minimumHeight()))
                if self._resize_edge & Qt.Edge.BottomEdge.value: rect.setBottom(global_pos.y())
                self.setGeometry(rect)
                event.accept()
            elif self._drag_pos is not None:
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                event.accept()
        except Exception: pass

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._is_resizing = False
        self._resize_edge = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def closeEvent(self, event):
        self.config["window_x"] = self.x()
        self.config["window_y"] = self.y()
        self.config["window_width"] = self.width()
        self.config["window_height"] = self.height()
        save_config(self.config)
        event.accept()
