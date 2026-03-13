"""
Stealth screen reader for capturing coding questions from the screen.

Two-tier strategy:
  1. macOS Accessibility API (AX) — reads text directly from UI elements.
     Zero pixels captured, invisible to proctoring and screen recording.
  2. Screenshot + local OCR (pytesseract) — fallback for apps that block AX.
     Captures only the frontmost window, excludes our overlay.
"""

import time
import os
import re
from typing import Optional, Tuple

CONTENT_ROLES = {
    "AXStaticText", "AXTextArea", "AXTextField",
    "AXWebArea", "AXScrollArea",
}


# ─── Tier 1: Accessibility API ───────────────────────────────────────────────

def _ax_get_frontmost_pid() -> Optional[int]:
    """Get the PID of the frontmost (focused) application."""
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return app.processIdentifier() if app else None
    except Exception:
        return None


def _ax_walk_element(element, texts: list, depth: int = 0, max_depth: int = 30):
    """
    Recursively walk the AX element tree and collect text from content roles.
    Only reads from semantic text elements (static text, text areas, web content)
    to avoid collecting incidental UI labels like button names or toolbar titles.
    """
    if depth > max_depth:
        return

    try:
        from ApplicationServices import (
            AXUIElementCopyAttributeValue,
            kAXValueAttribute,
            kAXChildrenAttribute,
            kAXRoleAttribute,
        )

        # Get the role of this element
        err_r, role = AXUIElementCopyAttributeValue(element, kAXRoleAttribute, None)
        role_str = role if (err_r == 0 and isinstance(role, str)) else ""

        # Only collect value from content-bearing roles
        if role_str in CONTENT_ROLES:
            err, value = AXUIElementCopyAttributeValue(element, kAXValueAttribute, None)
            if err == 0 and isinstance(value, str) and value.strip():
                stripped = value.strip()
                if stripped not in texts:
                    texts.append(stripped)

        # Always recurse into children (containers like AXGroup, AXScrollArea)
        err, children = AXUIElementCopyAttributeValue(element, kAXChildrenAttribute, None)
        if err == 0 and children:
            for child in children:
                _ax_walk_element(child, texts, depth + 1, max_depth)

    except Exception:
        pass


def _read_via_ax(pid: int) -> Optional[str]:
    """
    Extract all text from the frontmost window of the given PID using AX.
    Returns concatenated text or None if AX is unavailable/blocked.
    """
    try:
        from ApplicationServices import (
            AXUIElementCreateApplication,
            AXUIElementCopyAttributeValue,
            kAXWindowsAttribute,
            kAXFocusedWindowAttribute,
        )

        app_elem = AXUIElementCreateApplication(pid)

        # Try the focused window first, then fall back to first window
        err, window = AXUIElementCopyAttributeValue(
            app_elem, kAXFocusedWindowAttribute, None
        )
        if err != 0 or window is None:
            err, windows = AXUIElementCopyAttributeValue(
                app_elem, kAXWindowsAttribute, None
            )
            if err != 0 or not windows:
                return None
            window = windows[0]

        texts = []
        _ax_walk_element(window, texts)

        if not texts:
            return None

        # Deduplicate adjacent duplicates while preserving order
        seen = set()
        unique = []
        for t in texts:
            if t not in seen and t:
                seen.add(t)
                unique.append(t)

        return "\n".join(unique)

    except ImportError:
        return None
    except Exception:
        return None


# ─── Tier 2: Screenshot + OCR ────────────────────────────────────────────────

def _screenshot_frontmost_window() -> Optional["PIL.Image.Image"]:
    """
    Capture the contents of the frontmost window using Quartz.
    Our overlay (NSWindowSharingNone) is excluded automatically.
    Returns a PIL Image or None.
    """
    try:
        import Quartz
        from PIL import Image
        import io

        # Get the frontmost window's windowID
        window_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )

        if not window_list:
            return None

        # Skip our own app — find the frontmost non-InterviewAgent window
        target_window = None
        for win in window_list:
            owner = win.get("kCGWindowOwnerName", "")
            layer = win.get("kCGWindowLayer", 999)
            # Layer 0 = normal app windows; skip menu bar (layer < 0 on some systems)
            if owner != "InterviewAgent" and layer == 0:
                target_window = win
                break

        if target_window is None:
            return None

        window_id = target_window.get("kCGWindowNumber")

        # Capture that specific window
        image_ref = Quartz.CGWindowListCreateImage(
            Quartz.CGRectNull,  # capture only the window bounds
            Quartz.kCGWindowListOptionIncludingWindow,
            window_id,
            Quartz.kCGWindowImageBestResolution,
        )

        if image_ref is None:
            return None

        # Convert CGImage → PIL Image
        width = Quartz.CGImageGetWidth(image_ref)
        height = Quartz.CGImageGetHeight(image_ref)
        bpr = Quartz.CGImageGetBytesPerRow(image_ref)
        data_provider = Quartz.CGImageGetDataProvider(image_ref)
        raw_data = Quartz.CGDataProviderCopyData(data_provider)

        pil_img = Image.frombytes("RGBA", (width, height), bytes(raw_data), "raw", "BGRA")
        return pil_img.convert("RGB")

    except ImportError:
        return None
    except Exception:
        return None


def _ocr_image(image: "PIL.Image.Image") -> Tuple[Optional[str], Optional[str]]:
    """
    Run pytesseract OCR on a PIL image. Returns (text, error) tuple.
    """
    try:
        import pytesseract

        # Check if tesseract is installed
        try:
            pytesseract.get_tesseract_version()
        except pytesseract.TesseractNotFoundError:
            return None, "Tesseract executable not found. Please install it."

        # Boost contrast slightly for better OCR on dark-background coding IDEs
        from PIL import ImageEnhance
        image = ImageEnhance.Contrast(image).enhance(1.4)
        text = pytesseract.image_to_string(image, config="--psm 6")

        stripped_text = text.strip() if text else ""

        # Pytesseract can return empty strings or just whitespace.
        # It can also return error messages as strings. A simple heuristic:
        # if the text is short and contains 'error', it's probably not valid.
        if not stripped_text:
            return None, "OCR produced no text."

        if "error" in stripped_text.lower() and len(stripped_text) < 150:
            return None, f"OCR returned a potential error: {stripped_text}"

        return stripped_text, None

    except ImportError:
        return None, "Pytesseract library not installed. Please run 'pip install pytesseract'."
    except Exception as e:
        # Catch other potential errors from pytesseract/PIL
        return None, f"OCR process failed: {str(e)}"


# ─── Public API ──────────────────────────────────────────────────────────────

def capture_text_from_screen() -> dict:
    """
    Capture question text from the current screen.

    Returns:
        {
            "text": str,          # extracted text
            "method": str,        # "accessibility" | "ocr" | "error"
            "error": str | None,  # error message if applicable
        }
    """
    # Tier 1: AX API
    pid = _ax_get_frontmost_pid()
    if pid is not None:
        ax_text = _read_via_ax(pid)
        # Accept any non-empty string from the AX tree.
        # _ax_walk_element now only collects semantic content roles (text areas,
        # static text, web areas), so incidental button labels are already excluded.
        if ax_text and ax_text.strip():
            cleaned = re.sub(r"\n{3,}", "\n\n", ax_text)
            return {"text": cleaned.strip(), "method": "accessibility", "error": None}

    # Tier 2: Screenshot + OCR
    image = _screenshot_frontmost_window()
    if image is not None:
        text, err = _ocr_image(image)
        if err:
            return {"text": "", "method": "ocr", "error": err}
        if text:
            return {"text": text, "method": "ocr", "error": None}

    return {
        "text": "",
        "method": "error",
        "error": "Could not capture screen content. Grant Accessibility permissions if needed.",
    }
