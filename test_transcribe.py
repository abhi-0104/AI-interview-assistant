import sys
import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEventLoop
from transcriber import Transcriber

def test_transcode():
    app = QApplication(sys.argv)
    print("Initializing Transcriber...")
    t = Transcriber()
    
    loop = QEventLoop()
    result = {"text": None}

    def on_ready(text):
        print(f"Transcription Ready: '{text}'")
        result["text"] = text
        loop.quit()

    def on_status(msg):
        print(f"[STATUS] {msg}")
        if "ready" in msg.lower() or "Provider ready" in msg:
            print("Sending dummy audio...")
            dummy_audio = np.random.normal(0, 0.1, 16000 * 2).astype(np.float32)
            t.transcribe(dummy_audio)

    t.transcription_ready.connect(on_ready)
    t.status_changed.connect(on_status)
    
    t.load_model()
    
    # Timeout after 10s
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(10000, loop.quit)
    
    loop.exec()
    print(f"Final Test Result: '{result['text']}'")

if __name__ == "__main__":
    test_transcode()
