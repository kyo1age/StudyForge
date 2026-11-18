from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict
from ...schemas import RESULT_SCHEMAS

@dataclass
class LlmResponse:
    data: Dict[str, Any]
    tokens_used: int
    model_name: str | None = None
    prompt_tokens: int | None = None
    candidates_tokens: int | None = None
    thoughts_tokens: int | None = None
    cost_usd: float | None = None

class LlmError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code

class LlmProvider(ABC):
    name: str = "base"
    @abstractmethod
    def generate(self, material_type: str, context: str) -> LlmResponse:
        pass

def validate_and_count(material_type: str, payload: Dict[str, Any], tokens_used: int) -> LlmResponse:
    schema = RESULT_SCHEMAS[material_type]
    validated = schema.model_validate(payload)
    return LlmResponse(data=validated.model_dump(), tokens_used=max(1, int(tokens_used)))
