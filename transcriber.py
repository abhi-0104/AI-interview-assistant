"""
Speech-to-text engine using faster-whisper.
Runs transcription in a background thread to avoid UI freezing.
"""

import numpy as np
import threading
from PyQt6.QtCore import QObject, pyqtSignal
from config import load_config


class Transcriber(QObject):
    """Transcribes audio chunks to text using faster-whisper."""

    # Emitted when transcription is complete
    transcription_ready = pyqtSignal(str)
    # Emitted on status changes
    status_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self._model = None
        self._model_lock = threading.Lock()
        self._loading = False

    def load_model(self):
        """Load the Whisper model in a background thread."""
        if self._model is not None or self._loading:
            return

        self._loading = True
        self.status_changed.emit("Loading Whisper model...")

        def _load():
            try:
                from faster_whisper import WhisperModel

                model_name = self.config.get("whisper_model", "base.en")
                self._model = WhisperModel(
                    model_name,
                    device="cpu",
                    compute_type="int8",
                )
                self.status_changed.emit("Whisper model ready")
            except Exception as e:
                self.status_changed.emit(f"❌ Model load failed: {str(e)[:50]}")
            finally:
                self._loading = False

        thread = threading.Thread(target=_load, daemon=True)
        thread.start()

    def transcribe(self, audio: np.ndarray):
        """
        Transcribe an audio chunk. Runs in background thread.
        Emits transcription_ready signal when done.
        """
        if self._model is None:
            self.status_changed.emit("⚠ Whisper model not loaded yet")
            return

        def _do_transcribe():
            try:
                with self._model_lock:
                    segments, info = self._model.transcribe(
                        audio,
                        beam_size=3,
                        language="en",
                        vad_filter=True,
                        vad_parameters=dict(
                            min_silence_duration_ms=500,
                            speech_pad_ms=200,
                        ),
                    )

                    text_parts = []
                    for segment in segments:
                        text = segment.text.strip()
                        if text:
                            text_parts.append(text)

                    full_text = " ".join(text_parts).strip()

                    if full_text and len(full_text) > 3:
                        # Filter out common Whisper hallucinations
                        hallucinations = {
                            "thank you", "thanks for watching",
                            "subscribe", "like and subscribe",
                            "thank you for watching", "you",
                            "the end", "bye",
                        }
                        if full_text.lower() not in hallucinations:
                            self.transcription_ready.emit(full_text)

            except Exception as e:
                self.status_changed.emit(f"❌ Transcription error: {str(e)[:50]}")

        thread = threading.Thread(target=_do_transcribe, daemon=True)
        thread.start()

    @property
    def is_ready(self) -> bool:
        return self._model is not None
