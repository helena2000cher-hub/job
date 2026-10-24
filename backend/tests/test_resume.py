import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from app.api.main import create_app
from app.careers import CareerOption, CareerSuggestions
from app.profile import load_profile, save_profile
from app.resume import ResumeError, ResumeForm, ResumeStore, extract_text, rtf_to_text
from tests.conftest import FakeLLM

RESUME = "Иванова Анна\nЖенщина, 30 лет\nОпыт работы: аналитик, BPMN, SQL. " * 10

PARSED = {
    "headline": "Бизнес-аналитик",
    "target_roles": ["Бизнес-аналитик", "Аналитик данных"],
    "skills": ["BPMN", "SQL"],
    "experience_years": 5,
    "seniority": "middle",
    "search_queries": ["бизнес-аналитик"],
}


def _zip(member: str, xml: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member, xml)
    return buffer.getvalue()


def test_docx_paragraphs():
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    xml = (
        f"<w:document {w}><w:body>"
        "<w:p><w:r><w:t>Опыт работы</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Аналитик,</w:t></w:r><w:r><w:t xml:space='preserve'> SQL</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    assert extract_text(_zip("word/document.xml", xml), "cv.DOCX") == "Опыт работы\nАналитик, SQL"


def test_odt_paragraphs_and_headings():
    ns = 'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
    xml = (
        f"<office:document-content {ns} xmlns:office='urn:x'><office:body>"
        "<text:h>Резюме</text:h><text:p>Навыки: <text:span>BPMN</text:span></text:p>"
        "</office:body></office:document-content>"
    )
    assert extract_text(_zip("content.xml", xml), "cv.odt") == "Резюме\nНавыки: BPMN"


def test_rtf_cyrillic_and_unicode():
    rtf = r"{\rtf1\ansi{\fonttbl{\f0 Arial;}}\f0 \'cf\'f0\'e8\'e2\'e5\'f2"
    rtf += r"\par \u1052?\u1080?\u1088? SQL}"
    assert rtf_to_text(rtf).split("\n") == ["Привет", "Мир SQL"]


def test_txt_in_windows_encoding_and_html():
    assert extract_text("Аналитик".encode("cp1251"), "cv.txt") == "Аналитик"
    page = "<html><style>p{}</style><body><h1>Анна</h1><p>SQL&nbsp;и BPMN</p></body></html>"
    assert extract_text(page.encode(), "cv.html") == "Анна\nSQL и BPMN"


@pytest.mark.parametrize(
    ("name", "data", "message"),
    [
        ("cv.doc", b"x", "docx"),
        ("cv.jpg", b"x", "не поддерживается"),
        ("cv.docx", b"not a zip", "повреждён"),
        ("cv.txt", b"   \n ", "не нашлось текста"),
    ],
)
def test_unreadable_files_explain_why(name, data, message):
    with pytest.raises(ResumeError, match=message):
        extract_text(data, name)


def test_form_to_text_like_hh():
    form = ResumeForm.model_validate(
        {
            "position": "Бизнес-аналитик",
            "experience": [
                {"company": "ООО Ромашка", "position": "Аналитик", "start": "03.2019",
                 "description": "Описывала процессы в BPMN"},
            ],
            "education": [{"institution": "ПГНИУ", "specialty": "Экономика", "year": "2012"}],
            "skills": ["BPMN", "SQL"],
        }
    )  # fmt: skip
    text = form.to_text()
    assert "Желаемая должность: Бизнес-аналитик" in text
    assert "03.2019 — по настоящее время. Аналитик, ООО Ромашка" in text
    assert "2012, ПГНИУ, Экономика" in text and "Ключевые навыки: BPMN, SQL" in text
    assert ResumeForm().is_empty() and not form.is_empty()


@pytest.fixture
def setup(tmp_path, profile):
    profile.skills = ["Python", "n8n"]  # вписаны вручную
    profile.target_roles = ["AI-инженер"]
    profile.search_mode = "both"
    profile.search_skills = ["n8n"]
    profile.careers = CareerSuggestions(options=[CareerOption(title="AI-инженер", kind="core")])
    profile_path = tmp_path / "profile.json"
    save_profile(profile, profile_path)
    llm = FakeLLM()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    client = TestClient(
        create_app(
            engine,
            profile_path,
            serve_frontend=False,
            llm_factory=lambda: llm,
            resume_path=tmp_path / "resume.pdf",
            resume_fetcher=lambda url: RESUME if "open" in url else _closed(),
        )
    )
    return client, llm, profile_path, tmp_path


def _closed():
    raise ResumeError("По ссылке не видно резюме — похоже, оно закрыто.")


def test_upload_file_rebuilds_profile_and_keeps_manual(setup):
    client, llm, profile_path, tmp_path = setup
    llm.answers = [PARSED]
    assert client.get("/api/resume").json() == {"source": None, "form": None}

    r = client.post("/api/resume/file?filename=cv.txt", content=RESUME.encode())

    assert r.status_code == 200
    data = r.json()
    assert data["source"]["kind"] == "file" and data["source"]["name"] == "cv.txt"
    saved = load_profile(profile_path)
    assert saved.skills == ["BPMN", "SQL", "Python", "n8n"]  # навыки добавились, ручные остались
    assert saved.target_roles == ["AI-инженер"]  # выбор профессий не перебит резюме
    assert saved.search_mode == "both" and saved.search_skills == ["n8n"]
    assert ResumeStore(tmp_path / "resume.pdf").text().startswith("Иванова Анна")  # для писем
    assert client.get("/api/resume").json()["source"]["kind"] == "file"


def test_upload_bad_file_is_400(setup):
    client, *_ = setup
    r = client.post("/api/resume/file?filename=cv.doc", content=b"x")
    assert r.status_code == 400 and "docx" in r.json()["detail"]


def test_link_open_and_closed(setup):
    client, llm, profile_path, _ = setup
    llm.answers = [PARSED]
    r = client.post("/api/resume/link", json={"url": "https://hh.ru/resume/open"})
    assert r.status_code == 200 and r.json()["source"]["kind"] == "link"

    r = client.post("/api/resume/link", json={"url": "https://hh.ru/resume/hidden"})
    assert r.status_code == 400 and "закрыто" in r.json()["detail"]


def test_form_save_build_and_prefill(setup):
    client, llm, profile_path, tmp_path = setup
    form = {"position": "Аналитик", "skills": ["BPMN"], "about": "Люблю порядок в данных. " * 5}

    assert client.put("/api/resume/form", json=form).json()["form"]["position"] == "Аналитик"
    assert client.post("/api/resume/form/build", json={"position": "x"}).status_code == 400

    llm.answers = [PARSED]
    r = client.post("/api/resume/form/build", json=form)
    assert r.status_code == 200 and r.json()["source"]["kind"] == "form"
    assert "Желаемая должность: Аналитик" in llm.chat_calls[0][1]
    assert ResumeStore(tmp_path / "resume.pdf").text().startswith("Желаемая должность")

    llm.answers = [{"position": "Бизнес-аналитик", "experience": [{"company": "Ромашка"}]}]
    prefill = client.post("/api/resume/form/prefill").json()
    assert prefill["experience"][0]["company"] == "Ромашка"
