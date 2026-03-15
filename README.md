# InterviewAgent

InterviewAgent is a macOS desktop overlay for live technical interviews. It listens to incoming audio, transcribes questions with Groq-hosted `whisper-large-v3-turbo`, captures visible text from the screen, and streams answer drafts from OpenRouter.

## What It Does

- Floating always-on-top PyQt overlay
- Speech-to-text with Groq-hosted Whisper Turbo
- Screen text capture through macOS Accessibility and OCR fallback
- Resume and project-context upload for personalized answers
- Local chat/session history stored in SQLite
- OpenRouter-backed answer generation

## Tech Stack

- Python
- PyQt6
- Groq Whisper API
- OpenRouter
- `sounddevice`
- `pytesseract`
- SQLite

## Requirements

- macOS
- Python 3.11 or newer
- `pip`
- OpenRouter API key
- Groq API key
- Optional: BlackHole 2ch for system-audio capture
- Optional: `tesseract` for OCR fallback

## Quick Start

1. Clone the repo and enter the project folder.

```bash
git clone <your-repo-url>
cd Cheat
```

2. Create a virtual environment.

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install Python dependencies.

```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root.

```env
OPENROUTER_API_KEY=your_openrouter_key_here
GROQ_API_KEY=your_groq_key_here
```

5. Optional but recommended system packages:

```bash
brew install blackhole-2ch
brew install tesseract
```

6. Start the app.

```bash
./run.sh
```

## Fastest Working Setup

For the lowest latency during an interview:

- Use Groq `whisper-large-v3-turbo` transcription
- Install BlackHole and route meeting audio through it
- Keep OCR as a fallback only
- Use a stable OpenRouter model in `.env` or config

This repo is already configured around that approach.

## Environment Variables

Two variables are required:

```env
OPENROUTER_API_KEY=your_openrouter_key_here
GROQ_API_KEY=your_groq_key_here
```

Notes:

- `.env` is ignored by git and stays local
- Do not commit API keys

## First Run Checklist

When the app opens, verify these items:

- The overlay window appears on screen
- The status bar shows the active audio input
- The Groq Whisper client finishes initializing
- OpenRouter responses stream into the answer panel

If you want system-audio capture from Zoom, Meet, or Teams, complete the BlackHole setup in [setup_audio.md](/Users/Stark0104/Desktop/Coding/PROJECTS/Cheat/setup_audio.md).

## macOS Permissions

Depending on how you use the app, macOS may ask for:

- Microphone access
- Accessibility access

Accessibility is needed for screen text capture. If denied, the app falls back to OCR when possible.

## Running the App

The simplest way:

```bash
./run.sh
```

What `run.sh` does:

- creates `venv` if needed
- installs dependencies
- checks for BlackHole
- checks for `tesseract`
- launches the app

You can also run it manually:

```bash
source venv/bin/activate
python main.py
```

## BlackHole Setup

BlackHole is optional, but it gives the best results for interview audio because it captures the interviewer directly from system output instead of relying on room audio.

Install:

```bash
brew install blackhole-2ch
```

Then follow the full setup guide in [setup_audio.md](/Users/Stark0104/Desktop/Coding/PROJECTS/Cheat/setup_audio.md).

## OCR Setup

OCR is only needed when Accessibility capture cannot read the on-screen text.

Install:

```bash
brew install tesseract
```

If OCR is missing, the rest of the app still works.

## Project Structure

- `main.py` - app entry point
- `overlay_window.py` - main overlay UI and interactions
- `audio_manager.py` - audio capture and silence-based chunking
- `transcriber.py` - Groq Whisper Turbo transcription
- `screen_reader.py` - Accessibility capture and OCR fallback
- `llm_client.py` - OpenRouter streaming client
- `context_manager.py` - resume/project ingestion and prompt context
- `storage_manager.py` - SQLite session storage
- `run.sh` - one-command launcher

## Troubleshooting

### App opens but no answers appear

- Check that `OPENROUTER_API_KEY` is set in `.env`
- Confirm the machine has internet access
- Verify the OpenRouter model is available

### No transcription appears

- Wait for the Groq Whisper client to finish initializing
- Confirm macOS microphone permissions are granted
- If using meeting audio, make sure BlackHole is configured correctly

### Screen capture does not work

- Grant Accessibility permissions in macOS Settings
- Install `tesseract` for OCR fallback

### OCR is slow or inaccurate

- Prefer Accessibility capture when possible
- Keep the target window in the foreground
- Increase text size on the source window if needed

## Privacy

- API keys are read from `.env`
- `.env` is ignored by git
- Uploaded documents and chat history are stored locally under `~/.interviewagent/`
- Transcription audio is sent to Groq for speech-to-text

## Notes

- The current OpenRouter default model is `qwen/qwen3-coder:free`
- The current transcription strategy is Groq `whisper-large-v3-turbo`
- For interview use, latency is usually dominated by silence detection plus LLM response time, not just transcription time
