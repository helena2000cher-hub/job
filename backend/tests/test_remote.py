import pytest

from app.collectors.remote import detect_remote


@pytest.mark.parametrize(
    ("employment", "text", "expected"),
    [
        ("Дистанционная (удаленная) работа", "Оператор", True),
        ("Полная занятость", "Формат: удалённая работа, гибкий график", True),
        ("Полная занятость", "Можно работать удаленно", True),
        ("Полная занятость", "Remote, полный день", True),
        ("Полная занятость", "Работа в офисе, удалённой работы нет", False),
        ("Полная занятость", "Не рассматриваем удалённый формат", False),
        ("Полная занятость", "Доставка в удалённые районы края", False),
        ("Полная занятость", "Кладовщик на склад", False),
        (None, "", False),
    ],
)
def test_detect_remote(employment, text, expected):
    assert detect_remote(employment, text) is expected
