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
from config import load_config, set_api_key, get_api_key, ensure_dirs


def check_api_key(app: QApplication) -> bool:
    """Prompt for Groq API key if not set."""
    key = get_api_key()
    if key:
        return True

    key, ok = QInputDialog.getText(
        None,
        "Groq API Key Required",
        "Enter your Groq API key (get one free at console.groq.com):",
    )
    if ok and key.strip():
        set_api_key(key.strip())
        return True

    QMessageBox.warning(
        None,
        "No API Key",
        "The app requires a Groq API key to generate responses.\n"
        "You can set it later in ~/.interviewagent/config.json",
    )
    return True  # Still allow app to open


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

    # Check API key
    check_api_key(app)

    # Create and show the overlay window
    window = OverlayWindow()
    window.show()

    # Apply stealth settings after window is shown (needs NSWindow to exist)
    QTimer.singleShot(500, window.apply_stealth)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
