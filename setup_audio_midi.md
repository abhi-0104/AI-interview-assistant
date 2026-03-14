# Internal Audio Capture Setup (macOS)

To capture the interviewer's voice directly from system audio without using a microphone, you must route your system output to a virtual loopback device (BlackHole) while still being able to hear it in your earphones.

## 1. Install BlackHole
If you haven't already, run this in your terminal:
```bash
brew install blackhole-2ch
```

## 2. Create a Multi-Output Device
1. Open **Audio MIDI Setup** (found in `Applications/Utilities` or via Spotlight).
2. Click the **+** icon in the bottom left and select **Create Multi-Output Device**.
3. In the right panel, check the boxes for:
   - **BlackHole 2ch**
   - **(Your Earphones/Headphones)**
4. Ensure **Drift Correction** is checked for BlackHole.

## 3. Set System Output
1. Open **System Settings** -> **Sound**.
2. Set **Output** to **Multi-Output Device**.
   - *Note: You can no longer control volume via keyboard when this is selected. Use the browser/application volume sliders.*

## 4. Configure System Service Overlay
1. Open the System Service Overlay.
2. In **Interview Mode**, right-click (or click) the **Source** label at the bottom.
3. Select **BlackHole 2ch** from the list.
4. Click **🎤 Start**.

The app will now "hear" everything you hear in your earphones directly from the system.
