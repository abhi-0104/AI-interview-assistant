"""
Stealth content extractor for capturing coding questions from the screen.
Support Accessibility API (Zero-Pixel) and Native macOS Vision OCR (Zero-Dependency).
Enhanced with detailed logging and sorting logic for accuracy.
"""

import time
import os
import re
import tempfile
from typing import Optional, Tuple

CONTENT_ROLES = {
    "AXStaticText", "AXTextArea", "AXTextField",
    "AXWebArea", "AXScrollArea",
}


# ─── Tier 1: Accessibility API (Zero-Pixel) ──────────────────────────────────

def _ax_get_frontmost_pid() -> Optional[int]:
    """Get the PID of the frontmost (focused) application."""
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        pid = app.processIdentifier() if app else None
        print(f"[AX] Frontmost App: {app.localizedName() if app else 'None'} (PID: {pid})")
        return pid
    except Exception as e:
        print(f"[AX] Error getting PID: {e}")
        return None


def _ax_walk_element(element, texts: list, depth: int = 0, max_depth: int = 30):
    """Recursively walk the AX tree."""
    if depth > max_depth:
        return

    try:
        from ApplicationServices import (
            AXUIElementCopyAttributeValue,
            kAXValueAttribute,
            kAXChildrenAttribute,
            kAXRoleAttribute,
        )

        err_r, role = AXUIElementCopyAttributeValue(element, kAXRoleAttribute, None)
        role_str = role if (err_r == 0 and isinstance(role, str)) else ""

        if role_str in CONTENT_ROLES:
            err, value = AXUIElementCopyAttributeValue(element, kAXValueAttribute, None)
            if err == 0 and isinstance(value, str) and value.strip():
                stripped = value.strip()
                if stripped not in texts:
                    texts.append(stripped)

        err, children = AXUIElementCopyAttributeValue(element, kAXChildrenAttribute, None)
        if err == 0 and children:
            for child in children:
                _ax_walk_element(child, texts, depth + 1, max_depth)
    except Exception:
        pass


def _read_via_ax(pid: int) -> Optional[str]:
    """Extract text via Accessibility API."""
    print(f"[AX] Attempting extraction for PID {pid}...")
    try:
        from ApplicationServices import (
            AXUIElementCreateApplication,
            AXUIElementCopyAttributeValue,
            kAXWindowsAttribute,
            kAXFocusedWindowAttribute,
        )

        app_elem = AXUIElementCreateApplication(pid)
        err, window = AXUIElementCopyAttributeValue(app_elem, kAXFocusedWindowAttribute, None)
        if err != 0 or window is None:
            err, windows = AXUIElementCopyAttributeValue(app_elem, kAXWindowsAttribute, None)
            if err != 0 or not windows:
                print("[AX] No windows found for app.")
                return None
            window = windows[0]

        texts = []
        _ax_walk_element(window, texts)

        if not texts:
            print("[AX] No content roles found in window tree.")
            return None

        seen = set()
        unique = []
        for t in texts:
            if t not in seen and t:
                seen.add(t)
                unique.append(t)

        print(f"[AX] Successfully extracted {len(unique)} text segments.")
        return "\n".join(unique)
    except Exception as e:
        print(f"[AX] Critical Error: {e}")
        return None


# ─── Tier 2: Native macOS Vision OCR (Zero-Dependency) ───────────────────────

def capture_text_from_screen(exclude_id: Optional[int] = None, ax_only: bool = False) -> dict:
    """Main extraction entry point. Supports Zero-Pixel AX and Native Vision OCR."""
    print("\n" + "="*40)
    print(f"[Capture] New Request (ExcludeID: {exclude_id}, AX-Only: {ax_only})")
    
    pid = _ax_get_frontmost_pid()
    if pid is not None:
        ax_text = _read_via_ax(pid)
        if ax_text and ax_text.strip():
            cleaned = re.sub(r"\n{3,}", "\n\n", ax_text)
            print("[Capture] Success via AX.")
            return {"text": cleaned.strip(), "method": "accessibility", "error": None}

    if ax_only:
        print("[Capture] AX failed, AX-Only mode active. Returning empty.")
        return {"text": "", "method": "accessibility", "error": "No content found via AX (AX-Only mode)"}

    print("[Capture] Falling back to Vision OCR...")
    return _read_via_vision(exclude_id)


def _read_via_vision(exclude_id: Optional[int] = None) -> dict:
    """Capture screen content and run native macOS Vision OCR."""
    print("[Vision] Initiating Native OCR...")
    try:
        from Quartz import (
            CGRectInfinite,
            CGWindowListCreateImage,
            kCGWindowListOptionOnScreenOnly,
            kCGWindowListExcludeDesktopElements,
            kCGWindowImageDefault,
        )
        import objc
        
        # Load Vision framework
        objc.loadBundle("Vision", bundle_path="/System/Library/Frameworks/Vision.framework", module_globals=globals())
        from Vision import VNImageRequestHandler, VNRecognizeTextRequest

        # 1. Capture screen image
        print("[Vision] Capturing Screen Image...")
        options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
        image_ref = CGWindowListCreateImage(
            CGRectInfinite,
            options,
            exclude_id or 0,
            kCGWindowImageDefault
        )

        if not image_ref:
            print("[Vision] Error: Screen capture returned Null.")
            return {"text": "", "method": "error", "error": "macOS failed to capture screen image."}

        # 2. Setup Vision Request
        # Store observations with their bounding boxes to sort them correctly
        observations_data = []

        def completion_handler(request, error):
            if error:
                print(f"[Vision] Request error: {error}")
                return
            
            results = request.results()
            print(f"[Vision] Found {len(results)} text blocks.")
            for observation in results:
                candidates = observation.topCandidates_(1)
                if candidates:
                    # Vision coordinates: 0,0 is bottom-left. 
                    # We want to sort primarily by Y (top to bottom) then X (left to right).
                    bbox = observation.boundingBox()
                    text = candidates[0].string()
                    observations_data.append({
                        "text": text,
                        "y": bbox.origin.y, # Higher Y is towards the top
                        "x": bbox.origin.x
                    })

        request = VNRecognizeTextRequest.alloc().initWithCompletionHandler_(completion_handler)
        request.setRecognitionLevel_(0)  # 0 = Accurate, 1 = Fast
        request.setUsesLanguageCorrection_(True)

        # 3. Perform Request
        handler = VNImageRequestHandler.alloc().initWithCGImage_options_(image_ref, None)
        print("[Vision] Running analysis...")
        success, error = handler.performRequests_error_([request], None)

        if not success:
            print(f"[Vision] Analysis failed: {error}")
            return {"text": "", "method": "vision", "error": f"Vision analysis failed: {error}"}

        # 4. Sort observations: 
        # Sort by Y descending (top to bottom), then X ascending (left to right)
        observations_data.sort(key=lambda d: (-d["y"], d["x"]))
        
        recognized_text = [d["text"] for d in observations_data]
        text = "\n".join(recognized_text)
        
        print(f"[Vision] Total characters extracted: {len(text)}")
        print("="*40 + "\n")
        return {"text": text.strip(), "method": "vision", "error": None}

    except Exception as e:
        print(f"[Vision] Crash: {e}")
        return {"text": "", "method": "error", "error": f"Vision Error: {str(e)}"}
