import numpy as np
from transcriber import Transcriber

def test_transcode():
    print("Initializing Transcriber...")
    t = Transcriber()
    
    print("Generating dummy audio (1 sec of silence)...")
    # 16000 Hz, 1 second of noise
    dummy_audio = np.random.normal(0, 0.01, 16000).astype(np.float32)
    
    print("Attempting transcription...")
    try:
        text = t.transcribe(dummy_audio)
        print(f"Result: '{text}'")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_transcode()
