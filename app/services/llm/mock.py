import re
from typing import List
from .base import LlmProvider, validate_and_count

_SENTENCE_RE = re.compile(r"\n\s*\n|(?<=[.!?])\s+")

def _sentences(text: str, limit: int = 40) -> List[str]:
    parts = [" ".join(part.split()) for part in _SENTENCE_RE.split(text)]
    return [part[:420] for part in parts if len(part) > 15][:limit] or [" ".join(text.split())[:200] or "—"]

def _title_from(sentences: List[str], fallback: str) -> str:
    for s in sentences:
        words = s.split()
        if 3 <= len(words) <= 12:
            return s.rstrip(".!?")[:120]
    return fallback[:120]

class MockLlmProvider(LlmProvider):
    name = "mock"
    def generate(self, material_type: str, context: str):
        sentences = _sentences(context)
        title = _title_from(sentences, "Учебный материал")
        tokens = max(1, len(context) // 4) + 120
        if material_type == "summary":
            sections, per = [], max(1, min(4, (len(sentences) + 2) // 3))
            for i in range(0, len(sentences), per):
                chunk = sentences[i:i+per]
                sections.append({"title": _title_from(chunk, f"Раздел {len(sections)+1}"),
                                 "points": [c[:300] for c in chunk[:5]]})
                if len(sections) >= 8: break
            return validate_and_count("summary", {"title": title, "sections": sections}, tokens)
        if material_type == "flashcards":
            cards = []
            for i in range(0, len(sentences)-1, 2):
                q_words = sentences[i].split()
                stem = " ".join(q_words[:max(2, len(q_words)//2)])
                cards.append({"question": f"Продолжите мысль: «{stem} …»", "answer": sentences[i]})
                if len(cards) >= 12: break
            if not cards:
                cards = [{"question":"Какую мысль передаёт этот фрагмент?","answer":sentences[0]}]
            return validate_and_count("flashcards", {"title":title,"cards":cards}, tokens)
        distractors = ["В выбранных страницах об этом не говорится", "Это противоречит материалу", "Это относится к другой теме"]
        questions = []
        for s in sentences[:10]:
            words = s.split()
            gap = max(1, len(words)//3)
            masked = " ".join(words[:gap]) + " …"
            options = [" ".join(words[gap:]) or s] + distractors
            prompt = f"Продолжите фразу: «{masked.strip()}»" if len(words) > 1 else "Какое слово встречается в тексте?"
            questions.append({"question":prompt,"options":options,"correct_index":0})
        return validate_and_count("quiz", {"title":title,"questions":questions}, tokens)
