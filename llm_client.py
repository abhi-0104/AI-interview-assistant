"""
Groq API client for ultra-fast LLM response generation.
Streams responses token-by-token using Llama 3.3 70B.
"""

import threading
from PyQt6.QtCore import QObject, pyqtSignal
from config import load_config, get_api_key
from context_manager import build_context_string


class LLMClient(QObject):
    """Groq-powered LLM client for interview answer generation."""

    # Emitted for each streamed token
    token_received = pyqtSignal(str)
    # Emitted when full response is complete
    response_complete = pyqtSignal(str)
    # Emitted when generation starts
    generation_started = pyqtSignal()
    # Status updates
    status_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self._client = None
        self._conversation_history = []
        self._is_generating = False
        self._should_stop = False
        self._current_thread = None

    def initialize(self):
        """Initialize the Groq client."""
        api_key = get_api_key()
        if not api_key:
            self.status_changed.emit("⚠ No Groq API key set")
            return False

        try:
            from groq import Groq
            self._client = Groq(api_key=api_key)
            self.status_changed.emit("Groq client ready")
            return True
        except Exception as e:
            self.status_changed.emit(f"❌ Groq init failed: {str(e)[:50]}")
            return False

    def _build_system_prompt(self) -> str:
        """Build the system prompt with uploaded context."""
        context = build_context_string(
            max_chars=self.config.get("max_context_tokens", 4000) * 3
        )

        base_prompt = """You are an expert interview assistant. Your role is to help answer interview questions accurately, concisely, and professionally.

RULES:
- Give direct, confident answers as if YOU are the candidate
- Keep answers concise but thorough (2-4 paragraphs max unless the question demands more)
- Use first person ("I have experience with...", "In my project...")
- For coding questions, provide clean, correct code with brief explanations
- For behavioral questions, use the STAR method (Situation, Task, Action, Result)
- Reference the candidate's actual resume and projects when relevant
- Never say "I don't know" — give the best possible answer
- Do NOT mention that you are an AI or assistant
- Format responses clearly with bullet points or numbered lists when appropriate"""

        if context:
            base_prompt += f"""

CANDIDATE'S BACKGROUND (use this to personalize answers):
{context}"""

        return base_prompt

    def generate_response(self, question: str):
        """
        Generate a response to the interview question.
        Streams tokens via signals. Runs in background thread.
        """
        if self._client is None:
            if not self.initialize():
                return

        if self._is_generating:
            self.stop_generation()

        self._is_generating = True
        self._should_stop = False

        # Add question to conversation history
        self._conversation_history.append({
            "role": "user",
            "content": question,
        })

        def _do_generate():
            full_response = ""
            try:
                self.generation_started.emit()
                self.status_changed.emit("🧠 Generating...")

                messages = [
                    {"role": "system", "content": self._build_system_prompt()},
                ]
                # Keep last 10 exchanges for context
                messages.extend(self._conversation_history[-20:])

                stream = self._client.chat.completions.create(
                    model=self.config.get("groq_model", "llama-3.3-70b-versatile"),
                    messages=messages,
                    temperature=0.3,
                    max_tokens=2048,
                    stream=True,
                )

                for chunk in stream:
                    if self._should_stop:
                        break

                    delta = chunk.choices[0].delta
                    if delta.content:
                        token = delta.content
                        full_response += token
                        self.token_received.emit(token)

                # Add response to conversation history
                if full_response:
                    self._conversation_history.append({
                        "role": "assistant",
                        "content": full_response,
                    })

                self.response_complete.emit(full_response)
                self.status_changed.emit("✅ Done")

            except Exception as e:
                error_msg = str(e)
                self.status_changed.emit(f"❌ LLM error: {error_msg[:50]}")
                self.response_complete.emit(f"[Error: {error_msg}]")
            finally:
                self._is_generating = False

        self._current_thread = threading.Thread(target=_do_generate, daemon=True)
        self._current_thread.start()

    def stop_generation(self):
        """Stop the current generation."""
        self._should_stop = True
        self._is_generating = False
        self.status_changed.emit("⏹ Generation stopped")

    def clear_history(self):
        """Clear conversation history for a new session."""
        self._conversation_history = []

    def get_conversation_history(self) -> list:
        """Get the current conversation history."""
        return list(self._conversation_history)

    @property
    def is_generating(self) -> bool:
        return self._is_generating
