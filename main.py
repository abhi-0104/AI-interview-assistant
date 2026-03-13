"""
Interview AI Agent — macOS Stealth Overlay Widget
Entry point. Initializes the app and applies stealth settings.
"""

import sys
import os

# Add project dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox
from PyQt6.QtCore import QTimer
from overlay_window import OverlayWindow
from config import (
    set_openrouter_api_key,
    get_openrouter_api_key,
    ensure_dirs,
)


def _prompt_for_key(title: str, prompt: str) -> tuple[str, bool]:
    return QInputDialog.getText(None, title, prompt)


def check_api_keys(app: QApplication) -> bool:
    """Prompt for the OpenRouter API key if missing."""
    if not get_openrouter_api_key():
        key, ok = _prompt_for_key(
            "OpenRouter API Key Required",
            "Enter your OpenRouter API key (used for answer generation):",
        )
        if ok and key.strip():
            set_openrouter_api_key(key.strip())

    if get_openrouter_api_key():
        return True

    QMessageBox.warning(
        None,
        "Missing API Key",
        "The app needs an OpenRouter API key for answer generation.\n"
        "You can add it later in .env.",
    )
    return True


def main():
    """Main entry point."""
    ensure_dirs()

    app = QApplication(sys.argv)
    app.setApplicationName("InterviewAgent")

    # Set global dark theme
    app.setStyleSheet("""
        QToolTip {
            background-color: #2a2a2f;
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 11px;
        }
        QInputDialog {
            background-color: #222;
        }
        QInputDialog QLabel {
            color: white;
        }
        QInputDialog QLineEdit {
            background-color: #333;
            color: white;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 6px;
        }
        QInputDialog QPushButton {
            background-color: #444;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 16px;
        }
        QInputDialog QPushButton:hover {
            background-color: #555;
        }
        QMessageBox {
            background-color: #222;
        }
        QMessageBox QLabel {
            color: white;
        }
        QMessageBox QPushButton {
            background-color: #444;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 16px;
            min-width: 60px;
        }
        QMessageBox QPushButton:hover {
            background-color: #555;
        }
    """)

    # Check API keys
    check_api_keys(app)

    # Create and show the overlay window
    window = OverlayWindow()
    window.show()

    # Apply stealth settings after window is shown (needs NSWindow to exist)
    QTimer.singleShot(500, window.apply_stealth)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
