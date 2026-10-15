"""Semantic similarity between the profile and vacancies, with vectors cached in the DB."""

import math

from sqlmodel import Session

from app.llm import LLM
from app.models import Vacancy, VacancyEmbedding

BATCH_SIZE = 32
MAX_CHARS = 2000  # хвост длинных описаний мало что добавляет к смыслу


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def vacancy_vectors(
    session: Session, vacancies: list[Vacancy], llm: LLM, model: str
) -> dict[str, list[float]]:
    """Vectors for the given vacancies; only new or changed texts are sent to the API."""
    result: dict[str, list[float]] = {}
    missing: list[Vacancy] = []
    for vacancy in vacancies:
        cached = session.get(VacancyEmbedding, vacancy.id)
        if cached and cached.model == model and cached.content_hash == vacancy.content_hash():
            result[vacancy.id] = cached.vector
        else:
            missing.append(vacancy)

    for i in range(0, len(missing), BATCH_SIZE):
        batch = missing[i : i + BATCH_SIZE]
        vectors = llm.embed([v.text[:MAX_CHARS] for v in batch])
        for vacancy, vector in zip(batch, vectors, strict=True):
            session.merge(
                VacancyEmbedding(
                    vacancy_id=vacancy.id,
                    model=model,
                    content_hash=vacancy.content_hash(),
                    vector=vector,
                )
            )
            result[vacancy.id] = vector
    session.flush()  # без commit: он сбросил бы загруженные поля вакансий
    return result
