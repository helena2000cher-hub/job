"""Matching pipeline: hard filters → semantic similarity → LLM scoring of the top candidates."""

import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.config import get_settings
from app.llm import LLM
from app.matching.embeddings import cosine, vacancy_vectors
from app.matching.filters import reject_reason
from app.matching.scorer import score_vacancy
from app.models import Match, Vacancy
from app.profile import Profile

log = logging.getLogger(__name__)

PARALLEL_REQUESTS = 4


@dataclass
class MatchReport:
    total: int = 0
    rejected: Counter[str] = field(default_factory=Counter)
    duplicates: int = 0
    scored: int = 0
    reused: int = 0
    failed: int = 0
    results: list[tuple[Vacancy, Match]] = field(default_factory=list)


def run_matching(
    session: Session, profile: Profile, llm: LLM, *, top_n: int = 30, rescore: bool = False
) -> MatchReport:
    settings = get_settings()
    report = MatchReport()
    vacancies = list(session.exec(select(Vacancy)))
    report.total = len(vacancies)

    # Одну вакансию часто размещают в нескольких регионах — оцениваем один экземпляр.
    unique: dict[tuple[str, str], Vacancy] = {}
    for vacancy in vacancies:
        reason = reject_reason(vacancy, profile.preferences)
        if reason:
            report.rejected[reason.split(":")[0]] += 1
            continue
        key = (" ".join(vacancy.title.lower().split()), (vacancy.company or "").lower())
        if key in unique:
            report.duplicates += 1
        if key not in unique or _newer(vacancy, unique[key]):
            unique[key] = vacancy
    candidates = list(unique.values())
    if not candidates:
        return report

    profile_vector = llm.embed([profile.matching_text()])[0]
    vectors = vacancy_vectors(session, candidates, llm, settings.embedding_model)
    similarity = {v.id: cosine(profile_vector, vectors[v.id]) for v in candidates}
    top = sorted(candidates, key=lambda v: similarity[v.id], reverse=True)[:top_n]

    fingerprint = profile.fingerprint()
    to_score: list[Vacancy] = []
    for vacancy in top:
        cached = session.get(Match, vacancy.id)
        fresh = (
            cached
            and cached.profile_fingerprint == fingerprint
            and cached.content_hash == vacancy.content_hash()
        )
        if fresh and not rescore:
            cached.similarity = similarity[vacancy.id]
            report.reused += 1
        else:
            to_score.append(vacancy)

    with ThreadPoolExecutor(PARALLEL_REQUESTS) as pool:
        futures = {pool.submit(score_vacancy, profile, v, llm): v for v in to_score}
        for future in as_completed(futures):
            vacancy = futures[future]
            try:
                assessment = future.result()
            except Exception as exc:  # одна сбойная вакансия не должна ронять весь прогон
                log.warning("scoring failed for %s: %s", vacancy.id, exc)
                report.failed += 1
                continue
            session.merge(
                Match(
                    vacancy_id=vacancy.id,
                    profile_fingerprint=fingerprint,
                    content_hash=vacancy.content_hash(),
                    similarity=similarity[vacancy.id],
                    model=settings.llm_model_fast,
                    **assessment,
                )
            )
            report.scored += 1
    session.commit()

    for vacancy in top:
        match = session.get(Match, vacancy.id)
        if match and match.profile_fingerprint == fingerprint:
            report.results.append((vacancy, match))
    report.results.sort(key=lambda pair: (pair[1].score, pair[1].similarity), reverse=True)
    return report


def _newer(a: Vacancy, b: Vacancy) -> bool:
    return (a.source_updated_at or a.fetched_at) > (b.source_updated_at or b.fetched_at)
