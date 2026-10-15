# Job Matcher

Личный сервис для поиска работы. Он собирает вакансии из открытых источников, сравнивает их
с профилем кандидата (навыки, опыт, зарплата, формат работы) и показывает, какие подходят
и **почему**.

> 🚧 В разработке. План и исследование — в [PLAN.md](PLAN.md).

## Возможности

- [x] Сбор вакансий из «Работы России» (открытый API trudvsem.ru)
- [x] Определение удалённых вакансий
- [ ] Профиль из резюме (LLM через polza.ai)
- [ ] Оценка совпадения с объяснением: что совпало, чего не хватает
- [ ] Веб-интерфейс: лента, карточка вакансии, трекер откликов
- [ ] Больше источников: Telegram, Хабр Карьера, Exa

## Стек

Python 3.12 · FastAPI · SQLModel/SQLite · httpx · pytest · ruff, позже React + Vite + Tailwind.

## Быстрый старт

```bash
cd backend
py -m venv .venv
.venv\Scripts\activate          # Windows; на Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
copy ..\.env.example ..\.env     # и заполнить ключи

# собрать вакансии аналитика в Пермском крае
python -m app.collect --query "аналитик"

# только удалённые, по всей России
python -m app.collect --query "аналитик" --all-regions --remote-only

pytest
```

## Структура

```
backend/app/
  collectors/   # источники вакансий (trudvsem, ...)
  models.py     # единая модель Vacancy
  storage.py    # сохранение с обновлением дублей
  collect.py    # CLI для сбора
data/           # локальная БД и резюме — не попадают в git
```

## Приватность

Резюме, база вакансий и ключи API хранятся только локально (`data/`, `.env`)
и в репозиторий не попадают.
