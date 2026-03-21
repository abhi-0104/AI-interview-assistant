"""
Main overlay window. 
Frameless, floating, semi-transparent, screen-capture resistant.
Final version with Modern Chat UI, interactive prompt, and context-aware flow.
"""

import sys
import hashlib
import time
import datetime
import html
import re
from ctypes import c_void_p
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTextEdit, QLabel, QSlider, QFileDialog, QInputDialog, QMessageBox,
    QListWidget, QListWidgetItem, QSplitter, QFrame, QMenu, QSizeGrip,
    QApplication, QGraphicsDropShadowEffect, QTextBrowser, QLineEdit
)
from PyQt6.QtCore import Qt, QPoint, pyqtSlot, QSize, QTimer, QPropertyAnimation, QEasingCurve, QUrl
from PyQt6.QtGui import QFont, QAction, QCursor, QColor, QTextCursor, QIcon, QGuiApplication

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
        self._current_gen_id = 0
        self._code_blocks = {}
        self._next_code_block_id = 0

        self.config = load_config()
        self.mode = self.config.get("app_mode", "interview")

        print(f"[UI] Initializing Chat-Enabled Overlay (Mode: {self.mode})")

        # Core components
        self.audio_mgr = AudioManager()
        self.transcriber = Transcriber()
        self.llm_client = LLMClient()

        self._setup_window()
        self._build_ui()

        # Timers
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self._run_passive_check)

        self._level_timer = QTimer(self)
        self._level_timer.timeout.connect(self._enforce_level)
        self._level_timer.start(1000)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)

        self._update_ui_for_mode() # Now safe to call
        self._connect_signals()

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
        self.expanded_height = max(self.config.get("window_height", 550), 550)

        self.setGeometry(
            self.config.get("window_x", 100),
            self.config.get("window_y", 100),
            self.toolbar_width,
            self.toolbar_height
        )
        self.setMinimumWidth(400)
        self.setMinimumHeight(self.toolbar_height)
        self.setWindowOpacity(self.config.get("window_opacity", 0.95))
        self._apply_global_cursor()

    def _apply_global_cursor(self):
        """Recursively force all widgets to use the Arrow cursor."""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        for w in self.findChildren(QWidget):
            w.setCursor(Qt.CursorShape.ArrowCursor)
            w.setMouseTracking(True)

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
                background-color: rgba(18, 18, 22, 245);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.12);
            }
            * {
                font-family: 'Inter', 'Segoe UI', 'San Francisco', sans-serif;
                cursor: arrow !important;
            }
        """)
        self.setCentralWidget(self.main_container)
        self._apply_global_cursor()
        self.setCursor(Qt.CursorShape.ArrowCursor)

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
        self.chat_list.setStyleSheet("""
            QListWidget { background: transparent; border: none; color: #aaa; font-size: 11px; cursor: arrow; }
            QListWidget::item { padding: 5px; border-bottom: 1px solid rgba(255,255,255,0.05); cursor: arrow; }
            QListWidget::item:selected { background: rgba(0, 255, 136, 0.1); color: #00ff88; cursor: arrow; }
        """)
        self.chat_list.itemClicked.connect(self._on_session_selected)
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

        self.logo_container = QWidget()
        logo_l = QHBoxLayout(self.logo_container)
        logo_l.setContentsMargins(0, 0, 10, 0)
        logo_l.setSpacing(5)

        self.logo_label = QLabel("👻 Phantom Help AI")
        self.logo_label.setStyleSheet("color: #00ff88; font-weight: bold; font-size: 14px; letter-spacing: -0.5px;")
        
        self.dot_label = QLabel("●") # Recording dot
        self.dot_label.setStyleSheet("color: #ff3c3c; font-size: 10px;")
        
        logo_l.addWidget(self.logo_label)
        logo_l.addWidget(self.dot_label)
        self.toolbar_layout.addWidget(self.logo_container)

        btn_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.06); color: white; border-radius: 13px;
                padding: 4px 12px; font-size: 12px; font-weight: 500; border: 1px solid rgba(255, 255, 255, 0.05);
            }
            QPushButton:hover { background-color: rgba(0, 255, 136, 0.12); border: 1px solid #00ff88; }
            QPushButton[active="true"] { background-color: rgba(0, 255, 136, 0.2); border: 1px solid #00ff88; color: #00ff88; }
        """

        # MODE TOGGLE
        self.mode_container = QFrame()
        self.mode_container.setStyleSheet("background: rgba(255,255,255,0.05); border-radius: 8px; padding: 2px;")
        self.mode_layout = QHBoxLayout(self.mode_container)
        self.mode_layout.setContentsMargins(0, 0, 0, 0)
        self.mode_layout.setSpacing(0)
        
        self.interview_btn = QPushButton("Interview")
        self.interview_btn.setCheckable(True)
        self.interview_btn.setStyleSheet(btn_style + "QPushButton { border: none; border-radius: 6px; }")
        
        self.assess_btn = QPushButton("Assessment")
        self.assess_btn.setCheckable(True)
        self.assess_btn.setStyleSheet(btn_style + "QPushButton { border: none; border-radius: 6px; }")
        
        self.interview_btn.clicked.connect(lambda: self._set_mode("interview"))
        self.assess_btn.clicked.connect(lambda: self._set_mode("assessment"))
        
        self.mode_layout.addWidget(self.interview_btn)
        self.mode_layout.addWidget(self.assess_btn)
        self.toolbar_layout.addWidget(self.mode_container)

        self.analyze_btn = QPushButton("Analyze Screen 🖥")
        self.analyze_btn.setStyleSheet(btn_style)
        self.analyze_btn.clicked.connect(self._capture_screen)
        self.toolbar_layout.addWidget(self.analyze_btn)

        self.chat_btn = QPushButton("Chat")
        self.chat_btn.setStyleSheet(btn_style)
        self.chat_btn.clicked.connect(self._toggle_history)
        self.toolbar_layout.addWidget(self.chat_btn)

        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setFixedSize(30, 30)
        self.mic_btn.setCheckable(True)
        self.mic_btn.setStyleSheet("""
            QPushButton { background: rgba(0, 255, 136, 0.1); border-radius: 15px; border: 1px solid #00ff88; color: #00ff88; }
            QPushButton:checked { background: rgba(255, 60, 60, 0.1); border: 1px solid #ff3c3c; color: #ff3c3c; }
        """)
        self.mic_btn.clicked.connect(self._toggle_mic)
        self.toolbar_layout.addWidget(self.mic_btn)

        self.toolbar_layout.addStretch()

        self.timer_label = QLabel("00:00")
        self.timer_label.setStyleSheet("""
            background: rgba(40,40,45,255); color: #fff; padding: 4px 10px; 
            border-radius: 6px; font-size: 12px; font-family: 'Menlo', monospace; font-weight: bold;
        """)
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
        self.chat_view.setOpenExternalLinks(False)
        self.chat_view.anchorClicked.connect(self._handle_chat_link)
        self.chat_view.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
                color: #e0e0e0;
                font-size: 12px;
                line-height: 1.6;
                cursor: arrow;
            }
        """)
        self.chat_view.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.pane_layout.addWidget(self.chat_view, 1)

        # Follow-up Input Box
        self.input_container = QFrame()
        self.input_container.setStyleSheet("background-color: rgba(255,255,255,0.05); border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);")
        self.input_layout = QHBoxLayout(self.input_container)
        self.input_layout.setContentsMargins(8, 5, 8, 5)

        self.prompt_box = QLineEdit()
        self.prompt_box.setPlaceholderText("Ask a follow-up or type a command...")
        self.prompt_box.setStyleSheet("background: transparent; border: none; color: white; font-size: 12px; padding: 5px; cursor: arrow;")
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
        
        # 1. Switch AI Model Submenu
        model_menu = menu.addMenu("🤖 Switch AI Model")
        models = [
            ("Gemini 3.1 Pro (Custom)", "google/gemini-3.1-pro-preview-customtools"),
            ("GPT-5.4 Mini", "openai/gpt-5.4-mini"),
            ("Llama 3.3 70B (Free)", "meta-llama/llama-3.3-70b-instruct:free"),
            ("Gemini 2.0 Flash", "google/gemini-2.0-flash-001"),
            ("GPT-4o Mini", "openai/gpt-4o-mini"),
        ]
        curr_model = self.config.get("openrouter_model")
        for label, m_id in models:
            is_curr = (m_id == curr_model)
            act = model_menu.addAction(f"{'● ' if is_curr else '  '}{label}")
            act.triggered.connect(lambda _, m=m_id: self._set_ai_model(m))

        # 2. Switch Audio Device Submenu
        audio_menu = menu.addMenu("🎤 Switch Audio Device")
        devices = self.audio_mgr.get_available_devices()
        curr_dev = self.audio_mgr.get_device_name()
        for dev in devices:
            is_curr = (dev["name"] == curr_dev)
            act = audio_menu.addAction(f"{'● ' if is_curr else '  '}{dev['name']}")
            act.triggered.connect(lambda _, idx=dev["index"]: self._set_audio_device(idx))

        menu.addSeparator()
        
        # 3. Actions
        menu.addAction("📂 Open History", self._toggle_history)
        menu.addAction("🔄 New Session", self._new_session)
        
        up_act = menu.addAction("📄 Load Document")
        up_act.triggered.connect(self._upload_resume)
        
        menu.addSeparator()
        exit_act = menu.addAction("✕ Exit")
        exit_act.triggered.connect(QApplication.instance().quit)
        
        menu.exec(QCursor.pos())

    def _set_ai_model(self, model_id):
        self.config["openrouter_model"] = model_id
        save_config(self.config)
        self.llm_client.config["openrouter_model"] = model_id
        self.status_label.setText(f"AI: {model_id.split('/')[-1]}")

    def _set_audio_device(self, device_index):
        self.audio_mgr.set_device(device_index)
        self.status_label.setText(f"Mic: {self.audio_mgr.get_device_name()[:15]}...")

    def _set_mode(self, mode):
        self.mode = mode
        self.config["app_mode"] = self.mode
        save_config(self.config)
        self._update_ui_for_mode()
        print(f"[UI] Mode switched to: {self.mode}")

    def _update_ui_for_mode(self):
        is_interview = (self.mode == "interview")
        self.interview_btn.setChecked(is_interview)
        self.interview_btn.setProperty("active", str(is_interview).lower())
        self.assess_btn.setChecked(not is_interview)
        self.assess_btn.setProperty("active", str(not is_interview).lower())
        
        # Style refresh
        self.interview_btn.style().unpolish(self.interview_btn)
        self.interview_btn.style().polish(self.interview_btn)
        self.assess_btn.style().unpolish(self.assess_btn)
        self.assess_btn.style().polish(self.assess_btn)
        
        self.mic_btn.setVisible(is_interview)
        self.status_label.setText(f"Mode: {self.mode.capitalize()}")
        
        if is_interview:
            self.auto_timer.stop()
            self.transcriber.load_model()
            self.audio_mgr.start_capture()
        else:
            self.audio_mgr.stop_capture()
            self.auto_timer.start(3000)

    def _toggle_mic(self):
        is_muted = self.mic_btn.isChecked()
        self.audio_mgr.set_muted(is_muted)
        self.mic_btn.setText("🔇" if is_muted else "🎤")

    def _toggle_mode(self):
        # Backward compatibility for settings menu
        self._set_mode("assessment" if self.mode == "interview" else "interview")

    def _run_passive_check(self):
        result = screen_reader.capture_text_from_screen(ax_only=True)
        text = result.get("text", "").strip()
        if not text: return
        current_hash = hashlib.md5(text.encode()).hexdigest()
        if current_hash != self._last_hash:
            print("[UI] Passive check content detected.")
            self._last_hash = current_hash
            self._on_context_change(text, is_capture=True)

    def _append_to_chat(self, text, role="ai", persist=True):
        """Append a message bubble to the chat display."""
        if persist and self._session_id:
            storage_manager.add_message(self._session_id, "user" if role == "user" else "ai", text)

        sanitized = html.escape(text).replace('\n', '<br>') if role == "user" else self._format_response(text)
        
        bubble_style = "margin: 8px 0;"
        if role == "user":
            html_chunk = f'''
            <div style="{bubble_style} text-align: left;">
                <span style="color: rgba(255,255,255,0.4); font-size: 10px; font-weight: bold;">USER / SCREEN</span><br>
                <div style="background-color: rgba(255,255,255,0.06); border-radius: 8px; padding: 10px; color: #ccc; font-size: 12px;">{sanitized}</div>
            </div>
            '''
        else:
            html_chunk = f'''
            <div style="{bubble_style}">
                {sanitized}
            </div>
            '''
        
        self._chat_html += html_chunk
        self.chat_view.setHtml(f"<html><body style='margin:10px;'>{self._chat_html}</body></html>")
        self.chat_view.verticalScrollBar().setValue(self.chat_view.verticalScrollBar().maximum())

    def _render_inline_markdown(self, text):
        escaped = html.escape(text)
        escaped = re.sub(r'`([^`\n]+)`', r'<code style="background: rgba(255,255,255,0.08); border-radius: 4px; padding: 1px 4px; font-family: Menlo, monospace; color: #9fffd0;">\1</code>', escaped)
        escaped = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', escaped)
        escaped = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<i>\1</i>', escaped)
        return escaped

    def _build_code_block_html(self, lang, code):
        code_id = self._next_code_block_id
        self._next_code_block_id += 1
        self._code_blocks[code_id] = code

        lang_label = html.escape(lang) if lang else "text"
        escaped_code = html.escape(code)
        return f'''
        <div style="background-color: #0d0d0f; border: 1px solid rgba(255,255,255,0.12); border-radius: 10px; margin: 12px 0; overflow: hidden;">
            <div style="padding: 8px 12px; background: rgba(255,255,255,0.04); border-bottom: 1px solid rgba(255,255,255,0.08);">
                <table width="100%" cellspacing="0" cellpadding="0">
                    <tr>
                        <td><span style="color: #00ff88; font-size: 10px; font-weight: bold; text-transform: uppercase;">{lang_label}</span></td>
                        <td align="right"><a href="copy://{code_id}" style="color: #9fffd0; text-decoration: none; font-size: 11px; font-weight: bold;">Copy</a></td>
                    </tr>
                </table>
            </div>
            <pre style="margin: 0; padding: 12px; white-space: pre-wrap; color: #d0d0d0; font-size: 12px; line-height: 1.5; font-family: Menlo, 'Courier New', monospace;">{escaped_code}</pre>
        </div>
        '''

    def _format_response(self, text):
        """Render direct responses with lightweight markdown and copyable code blocks."""
        parts = []
        last_index = 0

        for match in re.finditer(r'```(\w*)\n(.*?)\n```', text, flags=re.DOTALL):
            prefix = text[last_index:match.start()]
            if prefix:
                parts.append(self._format_markdown_text(prefix))
            parts.append(self._build_code_block_html(match.group(1), match.group(2).strip()))
            last_index = match.end()

        suffix = text[last_index:]
        if suffix:
            parts.append(self._format_markdown_text(suffix))

        if not parts:
            parts.append(self._format_markdown_text(text))

        return f'<div style="font-size: 13px; line-height: 1.65; color: #e0e0e0;">{"".join(parts)}</div>'

    def _format_markdown_text(self, text):
        lines = text.splitlines()
        html_parts = []
        in_list = False

        def close_list():
            nonlocal in_list
            if in_list:
                html_parts.append("</ul>")
                in_list = False

        for raw_line in lines:
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped:
                close_list()
                html_parts.append("<div style='height: 8px;'></div>")
                continue

            bullet_match = re.match(r'^[-*]\s+(.*)$', stripped)
            if bullet_match:
                if not in_list:
                    html_parts.append("<ul style='margin: 8px 0 8px 18px; padding: 0;'>")
                    in_list = True
                html_parts.append(f"<li style='margin: 4px 0;'>{self._render_inline_markdown(bullet_match.group(1))}</li>")
                continue

            close_list()

            heading_match = re.match(r'^(#{1,3})\s+(.*)$', stripped)
            if heading_match:
                level = len(heading_match.group(1))
                size = {1: "18px", 2: "16px", 3: "14px"}[level]
                html_parts.append(
                    f"<div style='margin: 10px 0 6px; font-size: {size}; font-weight: bold; color: #ffffff;'>{self._render_inline_markdown(heading_match.group(2))}</div>"
                )
                continue

            html_parts.append(f"<div style='margin: 4px 0;'>{self._render_inline_markdown(stripped)}</div>")

        close_list()
        return "".join(html_parts)

    @pyqtSlot(QUrl)
    def _handle_chat_link(self, url):
        if url.scheme() == "copy":
            try:
                code_id = int(url.path().lstrip("/"))
            except ValueError:
                return
            code = self._code_blocks.get(code_id)
            if code is not None:
                QGuiApplication.clipboard().setText(code)
                self.status_label.setText("Code copied")
            return

        if url.isValid():
            from PyQt6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)

    def _on_context_change(self, text, is_capture=False):
        print(f"[UI] Processing message. Expand: {not self._is_expanded}")
        if not self._is_expanded:
            self._toggle_expand()
        
        display_text = f"📷 Screen Capture ({len(text)} chars)" if is_capture else text
        
        # PERSIST: For capture, we want the RAW context saved, not just the "Screen Capture" note
        self._append_to_chat(display_text, role="user", persist=False)
        if self._session_id:
            storage_manager.add_message(self._session_id, "user", text)
        
        # Start AI response
        self._current_ai_text = ""
        self._current_gen_id += 1 # Sync generation ID
        self.llm_client.generate_response(text)

    def _send_follow_up(self):
        text = self.prompt_box.text().strip()
        if not text: return
        self.prompt_box.clear()
        self._on_context_change(text, is_capture=False)

    def _connect_signals(self):
        self.audio_mgr.audio_chunk_ready.connect(self.transcriber.transcribe)
        self.transcriber.transcription_ready.connect(self._on_transcription)
        self.transcriber.status_changed.connect(lambda s: self.status_label.setText(s))
        self.llm_client.token_received.connect(self._on_token)
        self.llm_client.response_complete.connect(self._on_response_complete)
        self.llm_client.status_changed.connect(lambda s: self.status_label.setText(s))
        self.audio_mgr.status_changed.connect(lambda s: self.status_label.setText(s))

    @pyqtSlot(str, int)
    def _on_token(self, token, gen_id):
        if gen_id != self._current_gen_id:
            return 

        self._current_ai_text += token
        # For streaming, we use a simpler version of formatter
        temp_text = self._format_response(self._current_ai_text)
        
        temp_html = f"<html><body style='margin:10px;'>{self._chat_html}<div style='margin-top:10px;'>{temp_text}</div></body></html>"
        self.chat_view.setHtml(temp_html)
        self.chat_view.verticalScrollBar().setValue(self.chat_view.verticalScrollBar().maximum())

    @pyqtSlot(str, int)
    def _on_response_complete(self, full_text, gen_id):
        if gen_id != self._current_gen_id:
            return
            
        # Permanently commit the full response to chat buffer & storage
        self._append_to_chat(full_text, role="ai", persist=True)

    def _capture_screen(self):
        self.status_label.setText("⌛ Analyzing...")
        QApplication.processEvents()
        exclude = None
        if self._ns_window:
            try: exclude = self._ns_window.windowNumber()
            except: pass
            
        # Context-Specific Extraction Strategy
        force = "vision" if self.mode == "interview" else "accessibility"
        result = screen_reader.capture_text_from_screen(exclude_id=exclude, force_method=force)
        
        text = result.get("text", "").strip()
        if text:
            self._on_context_change(text, is_capture=True)
        else:
            self.status_label.setText(f"⚠ {result.get('error','Empty')}")

    @pyqtSlot(str)
    def _on_transcription(self, text):
        self._on_context_change(text, is_capture=False)

    def _on_session_selected(self, item):
        session_id = item.data(Qt.ItemDataRole.UserRole)
        print(f"[UI] Opening session {session_id}")
        self._session_id = session_id
        self.llm_client.clear_history()
        self._chat_html = ""
        self.chat_view.clear()
        
        messages = storage_manager.get_session_messages(session_id)
        for msg in messages:
            # Reconstruct history for LLM
            self.llm_client._conversation_history.append({
                "role": "user" if msg["role"] == "user" else "assistant",
                "content": msg["content"]
            })
            # Re-render UI bubbles
            role = "user" if msg["role"] == "user" else "ai"
            display_text = msg["content"]
            if role == "user" and len(display_text) > 500: # Heuristic for captures
                display_text = f"📷 Screen Capture ({len(display_text)} chars)"
            self._append_to_chat(display_text, role=role, persist=False)
        
        self.status_label.setText(f"📂 Session {session_id} Loaded")
        if not self._is_expanded:
            self._toggle_expand()

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
            # 🛡 Stealth: Cursor never changes shape
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.main_container.setCursor(Qt.CursorShape.ArrowCursor)

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
            
            # Repaint cursor to ensure it stays an arrow
            if not self._is_resizing and not self._drag_pos:
                self.setCursor(Qt.CursorShape.ArrowCursor)
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
        if self._is_expanded:
            self.config["window_height"] = self.height()
        save_config(self.config)
        event.accept()
