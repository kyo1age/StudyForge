"""Pydantic schemas: request validation and LLM output validation."""
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, computed_field, field_validator

MaterialType = Literal["summary", "flashcards", "quiz"]
MATERIAL_TYPES = ("summary", "flashcards", "quiz")
ProviderName = Literal["mock", "openai", "gemini"]

class SettingsOut(BaseModel):
    provider: ProviderName
    configured_provider: str
    fallback_reason: str | None
    max_upload_bytes: int
    max_pdf_pages: int
    max_pages_per_generation: int
    generation_mode: ProviderName
    model_used: str

class QuotaOut(BaseModel):
    used: int
    limit: int
    remaining: int
    week_start: str

class PagePreview(BaseModel):
    page_num: int
    text_preview: str

class DocumentOut(BaseModel):
    id: int
    filename: str
    size: int
    page_count: int
    status: str
    created_at: str

class DocumentDetailOut(DocumentOut):
    pages: List[PagePreview]
    warnings: list[str] = Field(default_factory=list)

class GenerateIn(BaseModel):
    document_id: int
    page_from: int = Field(ge=1)
    page_to: int = Field(ge=1)
    material_type: MaterialType

    @field_validator("page_from", "page_to")
    @classmethod
    def sane_pages(cls, v: int) -> int:
        if v > 100000:
            raise ValueError("page number too large")
        return v

class GenerationOut(BaseModel):
    id: int
    document_id: int
    page_from: int
    page_to: int
    material_type: MaterialType
    result: Optional[dict] = None
    tokens_used: int
    created_at: str
    provider: ProviderName | None = None
    model_name: str | None = None
    prompt_tokens: int | None = None
    candidates_tokens: int | None = None
    thoughts_tokens: int | None = None
    cost_usd: float | None = None

    @computed_field
    @property
    def generation_mode(self) -> ProviderName | None:
        return self.provider

    @computed_field
    @property
    def model_used(self) -> str | None:
        return self.model_name

class JobOut(BaseModel):
    job_id: str
    status: str
    generation: Optional[GenerationOut] = None

class JobStatusOut(JobOut):
    error: str | None = None
    error_status: int | None = None

class SummarySection(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    points: List[str] = Field(min_length=1, max_length=20)

class SummaryResult(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    sections: List[SummarySection] = Field(min_length=1, max_length=30)

class Flashcard(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=2000)

class FlashcardsResult(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    cards: List[Flashcard] = Field(min_length=1, max_length=100)

class QuizQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    options: List[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)

class QuizResult(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    questions: List[QuizQuestion] = Field(min_length=1, max_length=50)

RESULT_SCHEMAS = {
    "summary": SummaryResult,
    "flashcards": FlashcardsResult,
    "quiz": QuizResult,
}
