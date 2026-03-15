"""
System audio capture via BlackHole virtual audio loopback.
Captures interviewer's voice from video call output.
Falls back to default microphone if BlackHole not found.
"""

import numpy as np
import sounddevice as sd
import threading
import time
from PyQt6.QtCore import QObject, pyqtSignal
from config import load_config


class AudioManager(QObject):
    """Manages system audio capture for speech recognition."""

    # Signal emitted when a speech chunk is ready for transcription
    audio_chunk_ready = pyqtSignal(np.ndarray)
    # Signal emitted when status changes
    status_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.sample_rate = self.config["sample_rate"]
        self.chunk_seconds = self.config["audio_chunk_seconds"]
        self.silence_threshold = self.config.get("silence_threshold", 0.001)
        self.silence_duration = self.config.get("silence_duration", 1.5)
        self.max_speech_duration = 10.0 # Force flush after 10s

        self._stream = None
        self._is_capturing = False
        self._is_paused = False
        self._audio_buffer = []
        self._silence_start = None
        self._has_speech = False
        self._speech_start_time = None
        self._zero_count = 0
        self._lock = threading.RLock()
        self._device_index = None
        self._device_name = "Unknown"

        self._find_audio_device()

    def _find_audio_device(self):
        """Find audio device. Prioritize default mic for now as requested."""
        devices = sd.query_devices()
        
        # Priority 1: Default Input (likely Mic)
        default_idx = sd.default.device[0]
        if default_idx is not None and default_idx >= 0:
            self._device_index = int(default_idx)
            self._device_name = devices[int(default_idx)]["name"]
            print(f"[Audio] Selected Primary Device: {self._device_name}")
            return

        # Fallback: Search for BlackHole
        for i, dev in enumerate(devices):
            name = dev["name"].lower()
            if "blackhole" in name and dev["max_input_channels"] > 0:
                self._device_index = i
                self._device_name = dev["name"]
                print(f"[Audio] Selected BlackHole: {self._device_name}")
                return
            else:
                self._device_index = None
                self._device_name = "Default Mic"
            self.status_changed.emit(
                f"⚠ BlackHole not found. Using: {self._device_name}"
            )

    def get_device_name(self) -> str:
        """Get the name of the active audio device."""
        return self._device_name

    def get_available_devices(self) -> list:
        """Get list of available input devices."""
        devices = sd.query_devices()
        input_devices = []
        for i, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                input_devices.append({"index": i, "name": dev["name"]})
        return input_devices

    def set_device(self, device_index: int):
        """Switch to a different audio input device."""
        was_capturing = self._is_capturing
        if was_capturing:
            self.stop_capture()

        devices = sd.query_devices()
        self._device_index = device_index
        self._device_name = devices[device_index]["name"]
        self.status_changed.emit(f"Switched to: {self._device_name}")

        if was_capturing:
            self.start_capture()

    def start_capture(self) -> bool:
        """Start capturing audio from the selected device. Returns True on success."""
        if self._is_capturing:
            return True

        self._is_paused = False
        self._audio_buffer = []
        self._silence_start = None
        self._has_speech = False
        self._zero_count = 0

        try:
            self._stream = sd.InputStream(
                device=self._device_index,
                channels=1,
                samplerate=self.sample_rate,
                dtype="float32",
                blocksize=int(self.sample_rate * 0.1),  # 100ms blocks
                callback=self._audio_callback,
            )
            self._stream.start()
            self._is_capturing = True  # Set AFTER successful stream start
            self.status_changed.emit("🎤 Listening...")
            return True
        except Exception as e:
            self._is_capturing = False
            self.status_changed.emit(f"❌ Audio error: {str(e)[:50]}")
            return False

    def stop_capture(self):
        """Stop audio capture."""
        self._is_capturing = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        # Flush any remaining audio
        self._flush_buffer()
        self.status_changed.emit("⏹ Stopped")

    def set_muted(self, muted: bool):
        """Mute/Unmute the capture. If muting, force flush the buffer."""
        self._is_paused = muted
        if muted:
            print("[Audio] Muted. Force flushing buffer...")
            self._flush_buffer()
            self.status_changed.emit("🔇 Muted")
        else:
            self.status_changed.emit("🎤 Listening...")

    def toggle_pause(self):
        """Toggle pause/resume of audio capture."""
        if not self._is_capturing:
            return

        self._is_paused = not self._is_paused
        if self._is_paused:
            self.status_changed.emit("⏸️ Paused")
        else:
            self._audio_buffer = []
            self._silence_start = None
            self._has_speech = False
            self.status_changed.emit("🎤 Listening...")

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def is_capturing(self) -> bool:
        return self._is_capturing

    def _audio_callback(self, indata, frames, time_info, status):
        """Called by sounddevice for each audio block."""
        if self._is_paused or not self._is_capturing:
            return

        audio = indata[:, 0].copy()

        with self._lock:
            # Check energy level for VAD
            energy = np.sqrt(np.mean(audio ** 2))
            
            # Debug: Log energy and a tiny sample of raw data
            if time.time() % 2.0 < 0.1: # Log roughly once per 2 seconds
                sample_snippet = [round(float(x), 4) for x in audio[:5]]
                print(f"[Audio] Device {self._device_index} ({self._device_name})")
                print(f"[Audio] Energy: {energy:.6f} | Data[0..5]: {sample_snippet}")

            # Privacy Permission Check (macOS silently zeroes the buffer if blocked)
            if energy == 0.0:
                self._zero_count += 1
                if self._zero_count == 50: # After ~5 seconds of absolute zeroes
                    print("[Audio] CRITICAL: macOS is blocking the microphone (Energy 0.0).")
                    self.status_changed.emit("❌ Mic Blocked or Muted in macOS")
            else:
                self._zero_count = 0

            if energy > self.silence_threshold:
                # Speech detected
                self._has_speech = True
                if self._speech_start_time is None:
                    self._speech_start_time = time.time()
                    self.status_changed.emit("🎤 Hearing Voice...")
                
                self._silence_start = None
                self._audio_buffer.append(audio)

                # Force flush if speech is too long (Real-time feedback)
                if time.time() - self._speech_start_time >= self.max_speech_duration:
                    print(f"[Audio] Max speech reached ({self.max_speech_duration}s). Flushing.")
                    self._flush_buffer()
            else:
                if self._has_speech:
                    # Silence after speech
                    self._audio_buffer.append(audio)
                    if self._silence_start is None:
                        self._silence_start = time.time()
                    elif time.time() - self._silence_start >= self.silence_duration:
                        # silence detected — flush buffer
                        self._flush_buffer()

    def _flush_buffer(self):
        """Send accumulated audio buffer for transcription."""
        with self._lock:
            if self._audio_buffer and self._has_speech:
                full_audio = np.concatenate(self._audio_buffer)
                # Only emit if we have enough audio (at least 0.5 seconds)
                if len(full_audio) > self.sample_rate * 0.5:
                    self.audio_chunk_ready.emit(full_audio)
            
            self._audio_buffer = []
            self._silence_start = None
            self._has_speech = False
            self._speech_start_time = None
