# AI Interview Assistant

AI Interview Assistant is a macOS desktop overlay for live technical interviews and online assessments. It can listen to audio, capture on-screen text, use your uploaded resume or project files as context, and stream answer drafts in a floating PyQt window.

## What It Does

- Floating always-on-top overlay window
- Live transcription with Groq Whisper
- Screen text capture with macOS Accessibility and Vision OCR
- OpenRouter-powered answer generation
- Resume and code/project context upload
- Local chat/session history stored in SQLite
- **Strategic Hacking**: Pre-configured system prompts for "Performance Mindset", the CLEAR framework, and the 30-second Rule.

## Platform Support

- macOS only
- Python 3.11 or newer recommended

This project depends on PyQt6, macOS Accessibility APIs, and Apple frameworks exposed through `pyobjc`, so it is not a cross-platform app.

## Requirements

You need:

- Python 3
- `pip`
- An OpenRouter API key
- A Groq API key

Optional but useful:

- BlackHole 2ch for cleaner meeting-audio capture
- Homebrew for installing optional macOS tools

## Quick Start

1. Clone the repository and enter the project folder.

```bash
git clone <your-repo-url>
cd AI-interview-assistant
```

2. Create and activate a virtual environment.

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies.

```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root.

```env
OPENROUTER_API_KEY=your_openrouter_key_here
GROQ_API_KEY=your_groq_key_here
```

5. Start the app.

```bash
./run.sh
```

That is the simplest supported launch path. `run.sh` creates the virtual environment if missing, installs dependencies, checks for BlackHole, and starts the app with [`syssvc.py`](/Users/Stark0104/Desktop/Coding/PROJECTS/AI-interview-assistant/syssvc.py).

## Manual Run

If you do not want to use the helper script:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python syssvc.py
```

## First-Run Setup

When you launch the app for the first time, check these items:

- The overlay window appears
- macOS prompts for Microphone access if you want audio capture
- macOS prompts for Accessibility access if you want screen text capture
- OpenRouter responses stream into the chat panel

If API keys are missing from `.env`, the app will interactively prompt you for them on the first launch and can store them in the macOS Keychain for security.

## macOS Permissions

The app may need:

- Microphone permission for live audio capture
- Accessibility permission for reading visible text from other apps

Without Accessibility access, screen capture reliability drops because the app has to depend on OCR-style fallback behavior instead of direct text extraction.

## Audio Setup

The app works with a normal microphone, but for interview calls BlackHole usually gives cleaner input because it can capture meeting audio from system output.

Install BlackHole with Homebrew:

```bash
brew install blackhole-2ch
```

After installing it, route your meeting audio through BlackHole and select `BlackHole 2ch` if needed. The app already prefers that device by default.

## Strategic Interviewing

The agent is built with an "Interview Hacks" system prompt that helps you:
- **Control the Script**: Treat questions as performances to lead the interviewer to your strengths.
- **Plant Anchors**: Use "hooks" in your answers to spark specific follow-up questions.
- **CLEAR Framework**: Automatically structures your stories using Context, Leadership, Execution, and Accomplishment.
- **30-Second Rule**: Prompts for concise, high-impact responses to avoid rambling.

## Advanced Audio Tuning

If the agent is triggering answers too early or too late, you can adjust these in `settings.json`:
- `silence_duration`: How long (in seconds) the agent waits for a gap in speech (Default: `1.5`).
- `max_speech_duration`: The hard limit (in seconds) before a transcript is forced (Default: `30.0`).

## Environment Variables

The project reads secrets from the local `.env` file:

```env
OPENROUTER_API_KEY=your_openrouter_key_here
GROQ_API_KEY=your_groq_key_here
```

Notes:

- `.env` stays local
- Do not commit API keys
- The app can also persist keys in macOS Keychain when set through the UI/config flow

## Running Options

Primary launcher:

```bash
./run.sh
```

Direct Python entrypoint:

```bash
source venv/bin/activate
python syssvc.py
```

There is also a bundled macOS app at [`SystemManager.app`](/Users/Stark0104/Desktop/Coding/PROJECTS/AI-interview-assistant/SystemManager.app), plus helper launch scripts such as [`launch_app.sh`](/Users/Stark0104/Desktop/Coding/PROJECTS/AI-interview-assistant/launch_app.sh) and [`launcher.applescript`](/Users/Stark0104/Desktop/Coding/PROJECTS/AI-interview-assistant/launcher.applescript). For most users, `./run.sh` is the easiest path.

## Where Data Is Stored

The app stores local data under:

`~/Library/Application Support/com.apple.SystemManagementService`

This includes:

- `settings.json`
- `data.db`
- uploaded documents under `docs/`

## Project Structure

- [`syssvc.py`](/Users/Stark0104/Desktop/Coding/PROJECTS/AI-interview-assistant/syssvc.py) - application entrypoint
- [`overlay_window.py`](/Users/Stark0104/Desktop/Coding/PROJECTS/AI-interview-assistant/overlay_window.py) - overlay UI and interaction logic
- [`audio_manager.py`](/Users/Stark0104/Desktop/Coding/PROJECTS/AI-interview-assistant/audio_manager.py) - audio device selection and capture
- [`transcriber.py`](/Users/Stark0104/Desktop/Coding/PROJECTS/AI-interview-assistant/transcriber.py) - Groq Whisper transcription
- [`screen_reader.py`](/Users/Stark0104/Desktop/Coding/PROJECTS/AI-interview-assistant/screen_reader.py) - Accessibility and Vision-based screen text extraction
- [`llm_client.py`](/Users/Stark0104/Desktop/Coding/PROJECTS/AI-interview-assistant/llm_client.py) - OpenRouter client and streaming responses
- [`context_manager.py`](/Users/Stark0104/Desktop/Coding/PROJECTS/AI-interview-assistant/context_manager.py) - uploaded document and project context handling
- [`storage_manager.py`](/Users/Stark0104/Desktop/Coding/PROJECTS/AI-interview-assistant/storage_manager.py) - SQLite session storage
- [`run.sh`](/Users/Stark0104/Desktop/Coding/PROJECTS/AI-interview-assistant/run.sh) - setup-and-run helper

## Troubleshooting

### The app does not start

- Make sure you are on macOS
- Make sure Python 3 and `pip` are installed
- Recreate the virtual environment and reinstall dependencies

```bash
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### The overlay opens but no AI answer appears

- Check `OPENROUTER_API_KEY` in `.env`
- Confirm the machine has internet access
- Try again with the default model configured in the app

### No transcription appears

- Check that `GROQ_API_KEY` is set in `.env`
- Grant microphone permission in macOS Settings
- If you are using meeting audio, verify the selected input device

### Screen capture does not work

- Grant Accessibility access in macOS Settings
- Keep the source window visible and focused

## Notes

- Default OpenRouter model: `qwen/qwen3-coder:free`
- Default transcription model: `whisper-large-v3-turbo`
- The main supported workflow is launching through `./run.sh`
