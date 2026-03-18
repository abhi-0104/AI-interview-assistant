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
    # Emitted for each streamed token (text, generation_id)
    token_received = pyqtSignal(str, int)
    # Emitted when full response is complete (text, generation_id)
    response_complete = pyqtSignal(str, int)
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
        self._current_gen_id = 0

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
        """Build the system prompt with uploaded context and identity enforcement."""
        context = build_context_string(
            max_chars=self.config.get("max_context_tokens", 4000) * 3
        )
        mode = self.config.get("app_mode", "interview")

        if mode == "assessment":
            base_prompt = """You are a highly efficient technical assessment engine.
RULES:
- Handle all inputs with high precision.
- Respond **ONLY** with the correct answer or option. 
- Do NOT explain or provide commentary unless explicitly asked.
- Do NOT mention that you are an AI."""
        else:
            base_prompt = """You are the CANDIDATE currently being interviewed. You must speak in the FIRST PERSON ('I', 'me', 'my').

CHRONOLOGICAL AWARENESS & IDENTITY:
1. You ARE the person described in the provided BACKGROUND context. 
2. **Current Status**: Look for the most recent date (e.g., 'Present'). If your current status is a student in a degree program, you MUST identify as a STUDENT. 
3. Do NOT call yourself an 'AI Engineer' or 'Professional' if the resume shows you are currently a student or if your projects are personal/self-made.
4. Use the specific dates in the resume to anchor your timeline. If asked 'Tell me about yourself', tell YOUR story as it appears on the paper.
5. NEVER say 'Based on the provided context'. Say 'I am currently...', 'In my latest project...', etc.
6. NEVER mention that you are an AI.
7. If information is missing, do NOT hallucinate a professional career. Stick to what is in the resume. If asked about something not there, say you haven't had the chance to work with that yet but you are eager to learn.

TONE: Professional, honest, and grounded in your actual current level of experience."""

        if context:
            base_prompt += f"\n\nYOUR BACKGROUND (RESUME/PROJECTS):\n{context}"
        else:
            base_prompt += "\n\n(Note: No resume/project context is available yet. Maintain a professional candidate persona.)"

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
        self._current_gen_id += 1
        gen_id = self._current_gen_id

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

                print(f"[LLM] Stream opened (Gen: {gen_id}), waiting for tokens...")
                token_count = 0
                for chunk in stream:
                    if self._should_stop or gen_id != self._current_gen_id:
                        print(f"[LLM] Stop/New Gen requested. Aborting Gen {gen_id}.")
                        break

                    try:
                        delta = chunk.choices[0].delta
                        token = delta.content or ""
                        if token:
                            full_response += token
                            self.token_received.emit(token, gen_id)
                            token_count += 1
                    except Exception as chunk_err:
                        print(f"[LLM] Chunk Error: {chunk_err}")
                        continue

                print(f"[LLM] Gen {gen_id} finished. Total tokens: {token_count}")

                if full_response and gen_id == self._current_gen_id:
                    self._conversation_history.append({
                        "role": "assistant",
                        "content": full_response,
                    })
                    self.response_complete.emit(full_response, gen_id)
                    self.status_changed.emit("✅ Done")
                else:
                    print(f"[LLM] Gen {gen_id} results discarded (stale).")

            except Exception as e:
                import traceback
                error_msg = str(e)
                print(f"[LLM] Critical Generation Error: {error_msg}")
                traceback.print_exc()
                
                if "429" in error_msg or "rate_limit" in error_msg.lower():
                    status = "⚠ Rate Limited (Free Tier). Try again in 60s or switch model."
                else:
                    status = f"❌ LLM error: {error_msg[:30]}"
                
                self.status_changed.emit(status)
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
