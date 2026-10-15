from app.profile import Profile, build_profile, load_profile, redact_pii, save_profile
from tests.conftest import FakeLLM


def test_redact_pii():
    text = "Иванова Анна\n+7 (963) 011-47-26 — связь\nanna@yandex.ru\nродилась 5 марта 1985\nPython"
    redacted = redact_pii(text)
    assert "963" not in redacted
    assert "anna@" not in redacted
    assert "1985" not in redacted
    assert "Python" in redacted


def test_build_profile_uses_smart_model_and_drops_empty_prefs():
    llm = FakeLLM(
        [
            {
                "headline": "Бизнес-аналитик",
                "target_roles": ["Бизнес-аналитик"],
                "skills": ["BPMN"],
                "preferences": {"remote_only": True, "salary_min": 110000, "regions": []},
            }
        ]
    )
    profile = build_profile("резюме +7 999 123-45-67", llm)

    assert profile.preferences.salary_min == 110000
    assert profile.preferences.stop_words  # пустые значения не затёрли дефолты
    _, user, smart = llm.chat_calls[0]
    assert smart is True
    assert "123-45-67" not in user


def test_profile_roundtrip_and_fingerprint(tmp_path):
    profile = Profile(headline="Аналитик", target_roles=["Аналитик"], skills=["SQL"])
    path = tmp_path / "profile.json"
    save_profile(profile, path)

    loaded = load_profile(path)
    assert loaded == profile
    assert loaded.fingerprint() == profile.fingerprint()
    loaded.skills.append("Python")
    assert loaded.fingerprint() != profile.fingerprint()


def test_extra_skills_reach_matching_text():
    profile = Profile(headline="А", target_roles=["А"], skills=["SQL"])
    assert "Дополнительно" not in profile.matching_text()
    profile.extra = "Make, Google Таблицы"
    assert "Дополнительно (нет в резюме): Make, Google Таблицы" in profile.matching_text()
