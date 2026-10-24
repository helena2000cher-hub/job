from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = f"sqlite:///{(DATA_DIR / 'jobs.db').as_posix()}"

    polza_api_key: str = ""
    polza_base_url: str = "https://polza.ai/api/v1/"
    llm_model_fast: str = "deepseek/deepseek-v4.1-flash"  # оценка вакансий и письма
    llm_model_smart: str = "anthropic/claude-haiku-5.5"  # разбор резюме (разово)
    embedding_model: str = "baai/bge-m3"

    exa_api_key: str = ""
    superjob_api_key: str = ""  # бесплатно: https://api.superjob.ru/register/

    default_region_code: str = "5900000000000"  # Пермский край
    default_town: str = "Пермь"  # для SuperJob

    # Веб-доступ. Пустой пароль — вход не нужен (локальная разработка), демо выключено.
    app_password: str = ""
    session_secret: str = ""  # подпись cookie; обязателен, если задан пароль
    cookie_secure: bool = False  # True за HTTPS (на сервере)
    demo_enabled: bool = True  # гостям без входа показывать демо на вымышленных данных
    demo_reset_hours: float = 6  # демо-песочница сбрасывается к исходным данным
    # Коммерческий режим: интерфейс не показывает стоимость и названия внутренних сервисов
    public_mode: bool = False

    # Регистрация пользователей (нужен включённый вход: APP_PASSWORD и SESSION_SECRET)
    registration_enabled: bool = True
    public_url: str = "http://localhost:8000"  # адрес сайта — для ссылок в письмах и OAuth
    yandex_client_id: str = ""  # https://oauth.yandex.ru/client/new
    yandex_client_secret: str = ""
    vk_client_id: str = ""  # https://id.vk.ru/about/business — кабинет VK ID
    smtp_host: str = ""  # пусто — письма пишутся в лог сервера
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    # Платные действия пользователя в день (владелец без лимитов)
    limit_refresh: int = 1
    limit_letter: int = 5
    limit_resume: int = 2
    limit_careers: int = 2
    limit_advice: int = 1
    limit_manual: int = 10  # «+ Добавить отклик» по ссылке подтягивает вакансию через Exa
    max_parallel_searches: int = 2  # поисков пользователей одновременно

    def limits(self) -> dict[str, int]:
        return {
            "refresh": self.limit_refresh,
            "letter": self.limit_letter,
            "resume": self.limit_resume,
            "careers": self.limit_careers,
            "advice": self.limit_advice,
            "manual": self.limit_manual,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
