"""
Speech-to-text engine using Groq Whisper Turbo.
Runs transcription in a background thread to avoid UI freezing.
"""

import io
import threading
import wave

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal
from config import GROQ_TRANSCRIPTION_MODEL, get_groq_api_key, load_config


class Transcriber(QObject):
    """Transcribes audio chunks to text using Groq's Whisper API."""

    # Emitted when transcription is complete
    transcription_ready = pyqtSignal(str)
    # Emitted on status changes
    status_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self._client = None  # For Groq
        self._model = None  # For local Whisper
        self._client_lock = threading.Lock() # For Groq client access
        self._model_lock = threading.Lock() # For local Whisper model access
        self._loading = False

    def load_model(self):
        """Load the Whisper model or Groq client in a background thread."""
        provider = self.config.get("transcription_provider", "whisper")
        
        if provider == "groq":
            # Groq doesn't need a local model loaded, just check API key
            if get_groq_api_key():
                # Initialize Groq client once if not already
                if self._client is None and not self._loading:
                    self._loading = True
                    self.status_changed.emit("Connecting to Groq Whisper...")
                    def _load_groq_client():
                        try:
                            from groq import Groq
                            self._client = Groq(api_key=get_groq_api_key())
                            self.status_changed.emit("Groq Provider ready")
                        except Exception as e:
                            self.status_changed.emit(f"❌ Groq client init failed: {str(e)[:50]}")
                        finally:
                            self._loading = False
                    thread = threading.Thread(target=_load_groq_client, daemon=True)
                    thread.start()
                elif self._client is not None:
                    self.status_changed.emit("Groq Provider ready")
                return
            else:
                self.status_changed.emit("❌ Groq API key missing")
                # Fallback to local whisper if Groq key is missing
                self.config["transcription_provider"] = "whisper"
                # Continue to load local whisper model

        # If provider is not groq (i.e., whisper) or groq key was missing
        if self._model is not None or self._loading:
            return

        self._loading = True
        self.status_changed.emit("Loading Whisper model...")

        def _load_local_model():
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

        thread = threading.Thread(target=_load_local_model, daemon=True)
        thread.start()

    def transcribe(self, audio: np.ndarray):
        """
        Transcribe an audio chunk. Runs in background thread.
        Emits transcription_ready signal when done.
        """
        provider = self.config.get("transcription_provider", "whisper")

        if provider == "groq":
            if self._client is None:
                self.status_changed.emit("⚠ Groq client not ready yet")
                return
            self._transcribe_groq(audio)
        else: # Default to local whisper
            if self._model is None:
                self.status_changed.emit("⚠ Whisper model not loaded yet")
                return
            self._transcribe_local(audio)

    def _audio_to_wav_bytes(self, audio: np.ndarray) -> io.BytesIO:
        """Convert float32 mono audio to a 16-bit PCM WAV file buffer."""
        sample_rate = int(self.config.get("sample_rate", 16000))
        clipped = np.clip(audio, -1.0, 1.0)
        pcm16 = (clipped * 32767).astype(np.int16)

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm16.tobytes())

        buffer.seek(0)
        buffer.name = "audio.wav"
        return buffer

    def _transcribe_groq(self, audio: np.ndarray):
        """Transcribe using Groq Cloud API."""
        def _do_groq():
            try:
                from groq import APIStatusError
                from config import get_groq_api_key

                audio_file = self._audio_to_wav_bytes(audio)
                model_name = self.config.get("whisper_model", "whisper-large-v3-turbo")
                language = self.config.get("transcription_language", "en")

                with self._client_lock:
                    response = self._client.audio.transcriptions.create(
                        file=audio_file,
                        model=model_name,
                        language=language,
                        response_format="verbose_json",
                        temperature=0,
                    )
                
                full_text = (getattr(response, "text", "") or "").strip()
                self._handle_result(full_text)

            except APIStatusError as e:
                message = ""
                response = getattr(e, "response", None)
                if response is not None:
                    try:
                        body = response.json()
                        message = body.get("error", {}).get("message", "")
                    except Exception:
                        pass
                detail = f"HTTP {e.status_code}"
                if message:
                    detail = f"{detail}: {message}"
                self.status_changed.emit(f"❌ Transcription error: {detail[:120]}")
            except Exception as e:
                self.status_changed.emit(f"❌ Transcription error: {str(e)[:50]}")

        thread = threading.Thread(target=_do_groq, daemon=True)
        thread.start()

    def _transcribe_local(self, audio: np.ndarray):
        """Transcribe using local faster-whisper."""
        def _do_transcribe_local():
            try:
                with self._model_lock:
                    segments_gen, _info = self._model.transcribe(
                        audio,
                        beam_size=3,
                        language="en",
                        vad_filter=True,
                        vad_parameters=dict(
                            min_silence_duration_ms=500,
                            speech_pad_ms=200,
                        ),
                    )
                    segments = list(segments_gen)

                text_parts = [seg.text.strip() for seg in segments if seg.text.strip()]
                full_text = " ".join(text_parts).strip()
                self._handle_result(full_text)

            except Exception as e:
                self.status_changed.emit(f"❌ Transcription error: {str(e)[:50]}")

        thread = threading.Thread(target=_do_transcribe_local, daemon=True)
        thread.start()

    def _handle_result(self, full_text: str):
        """Emit signal if text is valid and not a hallucination."""
        if full_text and len(full_text) > 3:
            hallucinations = {
                "thank you", "thanks for watching",
                "subscribe", "like and subscribe",
                "thank you for watching", "you",
                "the end", "bye",
            }
            if full_text.lower() not in hallucinations:
                self.transcription_ready.emit(full_text)

    @property
    def is_ready(self) -> bool:
        return self._client is not None or self._model is not None
