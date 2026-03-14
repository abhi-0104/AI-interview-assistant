"""
OpenRouter-backed LLM client for streaming interview responses.
Enhanced with detailed logging to track signal flow and API responses.
"""

import threading
import json
from PyQt6.QtCore import QObject, pyqtSignal
from config import load_config, get_openrouter_api_key
from context_manager import build_context_string


class LLMClient(QObject):
    """OpenRouter-powered LLM client for interview answer generation."""

    token_received = pyqtSignal(str)
    response_complete = pyqtSignal(str)
    generation_started = pyqtSignal()
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
        """Initialize the OpenRouter client."""
        print("[LLM] Initializing Client...")
        api_key = get_openrouter_api_key()
        if not api_key:
            print("[LLM] Error: No API Key found.")
            self.status_changed.emit("⚠ No OpenRouter API key set")
            return False

        try:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://localhost/interviewagent",
                    "X-Title": "Parakeet AI Help",
                },
            )
            print("[LLM] OpenRouter client ready.")
            self.status_changed.emit("OpenRouter client ready")
            return True
        except Exception as e:
            print(f"[LLM] Init Failed: {e}")
            self.status_changed.emit(f"❌ OpenRouter init failed: {str(e)[:50]}")
            return False

    def _build_system_prompt(self) -> str:
        """Build the system prompt with uploaded context."""
        context = build_context_string(
            max_chars=self.config.get("max_context_tokens", 4000) * 3
        )
        mode = self.config.get("app_mode", "interview")

        base_prompt = """You are a professional system assistant. Your role is to help answer technical and logic-based questions accurately and concisely.

RULES:
- Handle all inputs with high precision.
- For technical questions, provide clear, optimized code or detailed logic.
- Do NOT mention that you are an AI.
- Format responses clearly."""

        if mode == "assessment":
            base_prompt += """
- MODE: Assessment.
- STRICTION: If the input appears to be a Multiple Choice Question (MCQ), respond **ONLY** with the text or letter of the correct option. Do not explain unless specifically asked in the same input.
- Keep all other answers extremely brief and focused on the solution."""
        else:
            base_prompt += """
- MODE: Standard.
- Give direct, confident answers.
- For behavioral or logic questions, use the STAR methodology if applicable.
- Reference internal documentation/background when relevant."""

        if context:
            base_prompt += f"\n\nCANDIDATE'S BACKGROUND:\n{context}"

        return base_prompt

    def generate_response(self, question: str):
        """
        Generate a response to the interview question.
        Streams tokens via signals. Runs in background thread.
        """
        print(f"\n[LLM] New Question Received: {question[:100]}...")
        
        if self._client is None:
            if not self.initialize():
                return

        if self._is_generating:
            print("[LLM] Already generating. Stopping previous request.")
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
                print("[LLM] Starting background thread generation...")
                self.generation_started.emit()
                self.status_changed.emit("🧠 Generating...")

                system_prompt = self._build_system_prompt()
                messages = [{"role": "system", "content": system_prompt}]
                messages.extend(self._conversation_history[-20:])

                model = self.config.get("openrouter_model", "qwen/qwen3-coder:free")
                print(f"[LLM] Model: {model}")
                print(f"[LLM] Context messages: {len(messages)}")

                stream = self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=2048,
                    stream=True,
                )

                print("[LLM] Stream opened, waiting for tokens...")
                token_count = 0
                for chunk in stream:
                    if self._should_stop:
                        print("[LLM] Stop requested by user.")
                        break

                    try:
                        delta = chunk.choices[0].delta
                        token = delta.content or ""
                        if token:
                            full_response += token
                            self.token_received.emit(token)
                            token_count += 1
                            if token_count == 1:
                                print(f"[LLM] First token received: {repr(token)}")
                    except Exception as chunk_err:
                        print(f"[LLM] Chunk Error: {chunk_err}")
                        continue

                print(f"[LLM] Stream finished. Total tokens: {token_count}")

                if full_response:
                    self._conversation_history.append({
                        "role": "assistant",
                        "content": full_response,
                    })

                self.response_complete.emit(full_response)
                self.status_changed.emit("✅ Done")
                print("[LLM] Final response logged to history.")

            except Exception as e:
                import traceback
                error_msg = str(e)
                print(f"[LLM] Critical Generation Error: {error_msg}")
                traceback.print_exc()
                self.status_changed.emit(f"❌ LLM error: {error_msg[:30]}")
                self.response_complete.emit(f"[Error: {error_msg}]")
            finally:
                self._is_generating = False
                print("[LLM] Thread cleanup complete.\n")

        self.thread = threading.Thread(target=_do_generate, daemon=True)
        self.thread.start()

    def stop_generation(self):
        self._should_stop = True
        self._is_generating = False
        print("[LLM] Stop command sent.")

    def clear_history(self):
        print("[LLM] History cleared.")
        self._conversation_history = []

    def get_conversation_history(self) -> list:
        return list(self._conversation_history)

    @property
    def is_generating(self) -> bool:
        return self._is_generating
