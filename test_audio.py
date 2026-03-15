import sounddevice as sd
import numpy as np

def test_mic():
    print("Available devices:")
    print(sd.query_devices())
    
    device_idx = sd.default.device[0]
    print(f"\nTesting default input device: {device_idx}")
    
    duration = 3  # seconds
    fs = 16000
    print(f"Recording {duration} seconds...")
    try:
        recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32', device=device_idx)
        sd.wait()
        energy = np.sqrt(np.mean(recording**2))
        max_val = np.max(np.abs(recording))
        print(f"Energy: {energy:.6f}")
        print(f"Max Amplitude: {max_val:.6f}")
        if energy == 0.0:
            print("WARNING: Received absolute silence. This usually indicates a macOS Microphone Permission block, OR the device is muted at the hardware/OS level.")
        else:
            print("SUCCESS: Received audio data!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_mic()
