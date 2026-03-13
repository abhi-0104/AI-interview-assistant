# BlackHole Audio Setup Guide

The Interview Agent captures the interviewer's voice directly from your system audio output using **BlackHole** — a free virtual audio loopback driver for macOS.

## Why BlackHole?

In a video call (Zoom, Google Meet, Teams), the interviewer's voice comes through your device speakers/headphones. BlackHole creates a virtual audio device that lets our app "listen" to this system audio output directly — crystal clear, no ambient noise.

**Bonus:** Your own voice is naturally filtered out since video calls don't play your voice back to you.

## One-Time Setup (5 minutes)

### Step 1: Install BlackHole

```bash
brew install blackhole-2ch
```

Or download from: https://existential.audio/blackhole/

### Step 2: Create Multi-Output Device

1. Open **Audio MIDI Setup** (search in Spotlight or find in `/Applications/Utilities/`)
2. Click the **+** button at bottom left → **Create Multi-Output Device**
3. Check **both**:
   - ✅ Your speakers or headphones (e.g., "MacBook Pro Speakers" or "AirPods")
   - ✅ **BlackHole 2ch**
4. Right-click the new Multi-Output Device → **Use This Device For Sound Output**

### Step 3: Verify

1. Play any YouTube video — you should hear audio through your speakers normally
2. Launch the Interview Agent — it should show "Using: BlackHole 2ch" in the status bar

## How It Works

```
Interviewer speaks → Zoom/Meet/Teams audio output
                            ↓
                    Multi-Output Device
                     ↙           ↘
              Your Speakers    BlackHole 2ch
              (you hear it)    (app captures it)
                                    ↓
                            Interview Agent
                            (transcribes → AI response)
```

## Troubleshooting

- **Can't hear audio after setup?** Make sure your speakers are checked in the Multi-Output Device
- **App shows "BlackHole not found"?** Restart the app after installing BlackHole
- **No transcription happening?** Check that BlackHole 2ch is checked in the Multi-Output Device, and that the Multi-Output Device is set as your system output
- **Want to switch back?** In System Settings → Sound → Output, select your regular speakers instead of Multi-Output Device

## After the Interview

Switch your system output back to your regular speakers/headphones in **System Settings → Sound → Output**. You only need the Multi-Output Device during interviews.
