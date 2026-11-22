"""Optional text generation. No provider is loaded unless explicitly enabled."""
from dataclasses import dataclass
from typing import Protocol, Optional

class TextProvider(Protocol):
    def complete(self, prompt: str, max_tokens: int) -> str: ...

@dataclass
class Budget:
    max_tokens: int
    used_tokens: int = 0

    def consume(self, estimated_tokens: int) -> bool:
        if estimated_tokens < 0 or self.used_tokens + estimated_tokens > self.max_tokens:
            return False
        self.used_tokens += estimated_tokens
        return True

class AIWriter:
    def __init__(self, enabled: bool = False, budget_tokens: int = 0, provider: Optional[TextProvider] = None):
        self.enabled=enabled
        self.budget=Budget(budget_tokens)
        self.provider=provider

    def draft(self, prompt: str, max_tokens: int = 200) -> Optional[str]:
        if not self.enabled or self.provider is None: return None
        reservation=min(max_tokens, self.budget.max_tokens-self.budget.used_tokens)
        if reservation <= 0 or not self.budget.consume(reservation): return None
        return self.provider.complete(prompt,reservation)
