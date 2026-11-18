"""Stricter Gemini output without changing the existing per-format wire shapes."""
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ...schemas import Flashcard, QuizQuestion, SummaryResult

_NOISE = re.compile(
    r"продолж(?:ите|и)\s+(?:фразу|предложение|мысль)|об этом не говорится"
    r"|это другая тема|в тексте не указано|нет правильного ответа"
    r"|все вышеперечислен(?:ное|ные)|название (?:файла|лекции|кафедры|факультета|вуза)"
    r"|титульн(?:ый|ого) лист|continue (?:the|this) (?:phrase|sentence|statement)"
    r"|(?:all|none) of the above|not (?:mentioned|stated) in the text"
    r"|(?:title|name) of the (?:file|lecture|department|university)|cover page"
    r"|сөйлемді жалғастыр|мәтінде айтылмаған|жоғарыдағылардың барлығы|дұрыс жауап жоқ"
    r"|(?:файлдың|дәрістің|кафедраның|университеттің) атауы"
)


def normalized(text):
    normalized_text = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    return " ".join(re.findall(r"[^\W_]+", normalized_text))


def verify_text(text, minimum):
    key = normalized(text)
    if len(key) < minimum or _NOISE.search(key):
        raise ValueError("Empty, too short, or boilerplate content")
    return text.strip()


class GeminiSummary(SummaryResult):
    detected_language: Literal["kk", "ru", "en", "other"]
    main_topics: list[str] = Field(min_length=1, max_length=12)

    @field_validator("main_topics")
    @classmethod
    def meaningful_topics(cls, topics):
        return [verify_text(topic, 1) for topic in topics]


class GeminiFlashcard(Flashcard):
    source_page: int = Field(ge=1)

    @field_validator("question", "answer")
    @classmethod
    def meaningful(cls, text):
        return verify_text(text, 5)


class GeminiFlashcards(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    detected_language: Literal["kk", "ru", "en", "other"]
    cards: list[GeminiFlashcard] = Field(min_length=1, max_length=20)

    @field_validator("cards")
    @classmethod
    def unique_questions(cls, cards):
        if len({normalized(card.question) for card in cards}) != len(cards):
            raise ValueError("Duplicate flashcards")
        return cards


class GeminiQuestion(QuizQuestion):
    explanation: str = Field(min_length=10, max_length=1000)
    source_page: int = Field(ge=1)
    correct_index: int = Field(strict=True, ge=0, le=3)

    @field_validator("question", "explanation")
    @classmethod
    def meaningful(cls, text):
        return verify_text(text, 10)

    @field_validator("options")
    @classmethod
    def unique_options(cls, options):
        cleaned = [verify_text(option, 1) for option in options]
        if len({normalized(option) for option in cleaned}) != len(cleaned):
            raise ValueError("Duplicate answer options")
        return cleaned


class GeminiQuiz(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    detected_language: Literal["kk", "ru", "en", "other"]
    questions: list[GeminiQuestion] = Field(min_length=1, max_length=10)

    @field_validator("questions")
    @classmethod
    def unique_questions(cls, questions):
        if len({normalized(item.question) for item in questions}) != len(questions):
            raise ValueError("Duplicate quiz questions")
        return questions


SCHEMAS = {"summary": GeminiSummary, "flashcards": GeminiFlashcards, "quiz": GeminiQuiz}

