from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import settings
from .db import init_db
from .routers import documents, generations, quota
from .schemas import SettingsOut
from .services.llm.factory import get_llm
from .services.llm.gemini_provider import configuration_error
from .services.upload_limit import UploadBodyLimit
from .security import SameOriginApi


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="StudyForge", version="2.1.0", lifespan=lifespan)
app.add_middleware(UploadBodyLimit)
app.add_middleware(SameOriginApi)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"], www_redirect=False)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/settings", response_model=SettingsOut, response_model_exclude_unset=True)
def public_settings():
    llm = get_llm()
    provider = llm.name
    reason = None
    if settings.LLM_PROVIDER == "openai" and provider == "mock":
        reason = "missing_api_key"
    elif settings.LLM_PROVIDER == "gemini" and provider == "mock":
        reason = configuration_error()
    elif settings.LLM_PROVIDER not in {"mock", "openai", "gemini"}:
        reason = "unsupported_provider"
    return SettingsOut(
        provider=provider,
        configured_provider=settings.LLM_PROVIDER if reason != "unsupported_provider" else "unknown",
        fallback_reason=reason,
        max_upload_bytes=settings.MAX_UPLOAD_BYTES,
        max_pdf_pages=settings.MAX_PDF_PAGES,
        max_pages_per_generation=settings.MAX_PAGES_PER_GENERATION,
        generation_mode=provider,
        model_used=getattr(llm, "model_name", "mock-generator"),
    )


app.include_router(quota.router)
app.include_router(documents.router)
app.include_router(generations.router)
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")

