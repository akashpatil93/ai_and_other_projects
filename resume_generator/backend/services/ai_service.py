from typing import List, Dict, Tuple


class AIService:
    def __init__(self, agent: str, api_key: str):
        self.agent = agent.lower()
        self.api_key = api_key

        if self.agent == "claude":
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        elif self.agent == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.genai = genai
            self.model = genai.GenerativeModel(
                "gemini-2.0-flash",
                system_instruction=(
                    "You are an expert resume writer and ATS optimization specialist."
                ),
            )
        else:
            raise ValueError(f"Unsupported agent: {agent}. Use 'claude' or 'gemini'.")

    def send_message(self, messages: List[Dict], system: str = "") -> str:
        if self.agent == "claude":
            return self._claude_chat(messages, system)
        elif self.agent == "gemini":
            return self._gemini_chat(messages)

    def _claude_chat(self, messages: List[Dict], system: str) -> str:
        import anthropic
        response = self.client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4096,
            system=system,
            messages=messages,
        )
        return response.content[0].text

    def _gemini_chat(self, messages: List[Dict]) -> str:
        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})

        chat = self.model.start_chat(history=history)
        response = chat.send_message(messages[-1]["content"])
        return response.text

    def validate_api_key(self) -> Tuple[bool, str]:
        """Validate the API key with a minimal test request."""
        try:
            if self.agent == "claude":
                self.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Hi"}],
                )
                return True, "Claude API key validated ✓"

            elif self.agent == "gemini":
                model = self.genai.GenerativeModel("gemini-2.0-flash")
                model.generate_content("Hi")
                return True, "Gemini API key validated ✓"

        except Exception as e:
            err = str(e)
            if "401" in err or "authentication" in err.lower() or "api key" in err.lower() or "unauthorized" in err.lower():
                return False, "Invalid API key. Please check and try again."
            return False, f"Validation failed: {err}"
