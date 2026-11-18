"""Central configuration. All values come from environment variables."""
import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_dotenv() -> None:
    """Minimal .env loader (avoids extra dependency)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


class Settings:
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = Path(os.environ.get("STUDYFORGE_DATA_DIR", BASE_DIR / "data")).resolve()
    DB_PATH: Path = DATA_DIR / "studyforge.db"
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    OCR_TESSDATA_DIR: Path = Path(os.environ.get("OCR_TESSDATA_DIR", DATA_DIR / "tessdata")).resolve()

    LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "mock").lower()
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    GEMINI_INPUT_PRICE_PER_1M: str = os.environ.get("GEMINI_INPUT_PRICE_PER_1M", "")
    GEMINI_OUTPUT_PRICE_PER_1M: str = os.environ.get("GEMINI_OUTPUT_PRICE_PER_1M", "")
    GEMINI_DAILY_REQUEST_LIMIT: str = os.environ.get("GEMINI_DAILY_REQUEST_LIMIT", "30")
    GEMINI_DAILY_BUDGET_USD: str = os.environ.get("GEMINI_DAILY_BUDGET_USD", "2.00")

    WEEKLY_TOKEN_LIMIT: int = int(os.environ.get("WEEKLY_TOKEN_LIMIT", "100000"))
    MAX_UPLOAD_BYTES: int = int(os.environ.get("MAX_UPLOAD_MB", "20")) * 1024 * 1024
    MAX_PAGES_PER_GENERATION: int = int(os.environ.get("MAX_PAGES_PER_GENERATION", "60"))
    MAX_PDF_PAGES: int = 500
    MAX_EXTRACTED_CHARS: int = 2_000_000

    COOKIE_SECURE: bool = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
    CLIENT_COOKIE: str = "sf_client_id"

    TOKEN_CHARS_RATIO: int = 4


settings = Settings()
