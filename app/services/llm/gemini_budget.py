"""SQLite ledger for attempted Gemini requests, independent of document history."""
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation

from ...config import settings
from ...db import write
from .base import LlmError

_MICROS = 1_000_000


@dataclass(frozen=True)
class Budget:
    request_limit: int
    daily_micros: int
    input_price: Decimal
    output_price: Decimal

    @classmethod
    def from_settings(cls):
        try:
            request_limit = int(settings.GEMINI_DAILY_REQUEST_LIMIT)
            daily = Decimal(settings.GEMINI_DAILY_BUDGET_USD)
            input_price = Decimal(settings.GEMINI_INPUT_PRICE_PER_1M)
            output_price = Decimal(settings.GEMINI_OUTPUT_PRICE_PER_1M)
            if not (0 <= request_limit <= 100_000 and 0 <= daily <= 1_000_000
                    and 0 < input_price <= 100_000 and 0 < output_price <= 100_000):
                raise ValueError("Invalid Gemini budget")
            ceiling = int((daily * _MICROS).to_integral_value(rounding=ROUND_FLOOR))
            return cls(request_limit, ceiling, input_price, output_price)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Invalid Gemini budget") from exc

    def cost(self, prompt_tokens, output_tokens):
        # USD per million tokens converts directly to microdollars per token.
        return int((self.input_price * prompt_tokens + self.output_price * output_tokens)
                   .to_integral_value(rounding=ROUND_CEILING))

    def reserve(self, cost_micros):
        day = datetime.now(UTC).date().isoformat()
        with write() as conn:
            count, spent = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(cost_microusd),0) FROM gemini_attempts WHERE day_utc=?",
                (day,),
            ).fetchone()
            if count >= self.request_limit:
                raise LlmError("Исчерпан дневной лимит запросов AI-провайдера.", 429)
            if spent + cost_micros > self.daily_micros:
                raise LlmError("Недостаточно дневного бюджета AI-провайдера для этого запроса.", 429)
            return conn.execute("INSERT INTO gemini_attempts(day_utc, cost_microusd) VALUES (?,?)",
                                (day, cost_micros)).lastrowid


def settle_attempt(attempt_id, cost_micros):
    with write() as conn:
        conn.execute("UPDATE gemini_attempts SET cost_microusd=? WHERE id=?", (cost_micros, attempt_id))

