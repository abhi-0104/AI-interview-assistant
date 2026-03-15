import sys
import numpy as np
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from transcriber import Transcriber

def test():
    app = QApplication(sys.argv)
    t = Transcriber()
    
    def on_status(msg):
        print(f"[STATUS] {msg}")
        if msg == "Groq Whisper ready":
            print("[TEST] Generating audio and testing transcription...")
            # Let's write an actual sinewave that sounds like a tone, or just load real audio.
            # But the transcriber expects 16kHz float32. 
            # Silence might be filtered by VAD. 
            audio = np.random.normal(0, 0.5, 16000 * 2).astype(np.float32)
            t.transcribe(audio)

    def on_ready(text):
        print(f"[TRANSCRIPTION] {text}")
        QApplication.quit()

    t.status_changed.connect(on_status)
    t.transcription_ready.connect(on_ready)

    print("[TEST] Loading model...")
    t.load_model()
    
    # Timeout after 60s
    QTimer.singleShot(60000, lambda: (print("[TEST] Timeout"), QApplication.quit()))
    sys.exit(app.exec())

if __name__ == "__main__":
    test()
