from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Vacancy
from app.storage import save_vacancies


def make(title: str, salary: int | None = None) -> Vacancy:
    return Vacancy(
        id="trudvsem:1",
        source="trudvsem",
        external_id="1",
        title=title,
        salary_from=salary,
        url="https://example.org/1",
        skills=["Excel"],
    )


def test_save_inserts_then_updates():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        first = save_vacancies(session, [make("Аналитик")])
        second = save_vacancies(session, [make("Старший аналитик", 90000)])

        rows = session.exec(select(Vacancy)).all()

    assert (first.created, first.updated) == (1, 0)
    assert (second.created, second.updated) == (0, 1)
    assert len(rows) == 1
    assert rows[0].title == "Старший аналитик"
    assert rows[0].salary_from == 90000
    assert rows[0].skills == ["Excel"]
