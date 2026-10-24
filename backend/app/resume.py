"""Resume sources: a file in any common format, a link, or a hand-filled form like on hh.ru.

Whatever the source, its text is saved next to the resume as resume.txt — the single source of
facts for the profile and cover letters.
"""

import html
import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree

import httpx
from pydantic import BaseModel, Field

from app.config import get_settings
from app.llm import LLM

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MIN_RESUME_CHARS = 300  # меньше — скорее всего закрытое резюме или страница входа

FILE_TYPES = {
    ".pdf": "PDF",
    ".docx": "Word",
    ".odt": "OpenDocument",
    ".rtf": "RTF",
    ".txt": "текст",
    ".md": "текст",
    ".html": "веб-страница",
    ".htm": "веб-страница",
}


class ResumeError(ValueError):
    """Понятная пользователю причина, почему резюме не удалось прочитать."""


# --- файлы ---


def extract_text(data: bytes, filename: str) -> str:
    """Text of a resume file: PDF, Word (.docx), OpenDocument, RTF, plain text or HTML."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".doc":
        raise ResumeError(
            "Старый формат Word (.doc) не читается. Откройте файл в Word и сохраните как .docx "
            "или PDF — или скачайте резюме с hh.ru сразу в PDF."
        )
    if suffix not in FILE_TYPES:
        raise ResumeError(
            f"Формат {suffix or 'без расширения'} не поддерживается. "
            "Подойдут: PDF, DOCX, ODT, RTF, TXT."
        )
    try:
        if suffix == ".pdf":
            text = _pdf_text(data)
        elif suffix == ".docx":
            text = _xml_text(data, "word/document.xml", paragraph="p", run_text="t")
        elif suffix == ".odt":
            text = _xml_text(data, "content.xml", paragraph=("p", "h"), run_text=None)
        elif suffix == ".rtf":
            text = rtf_to_text(_decode(data))
        elif suffix in (".html", ".htm"):
            text = html_to_text(_decode(data))
        else:
            text = _decode(data)
    except ResumeError:
        raise
    except Exception as exc:  # битый файл: pypdf/zip/xml бросают разное
        kind = FILE_TYPES[suffix]
        raise ResumeError(f"Не удалось прочитать файл ({kind}): он повреждён?") from exc
    text = _tidy(text)
    if not text:
        raise ResumeError(
            "В файле не нашлось текста. Если это скан или картинка — сохраните резюме "
            "как текстовый PDF или Word."
        )
    return text


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


def _xml_text(data: bytes, member: str, *, paragraph, run_text: str | None) -> str:
    """Paragraph texts from a zipped XML document (.docx, .odt) without extra libraries."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = ElementTree.fromstring(archive.read(member))
    paragraphs = (paragraph,) if isinstance(paragraph, str) else paragraph
    lines = []
    for element in root.iter():
        if _local(element.tag) not in paragraphs:
            continue
        if run_text is None:  # ODT: текст прямо в абзаце и вложенных span
            lines.append("".join(element.itertext()))
            continue
        parts = []
        for node in element.iter():
            tag = _local(node.tag)
            if tag == run_text and node.text:
                parts.append(node.text)
            elif tag == "tab":
                parts.append("\t")
            elif tag in ("br", "cr"):
                parts.append("\n")
        lines.append("".join(parts))
    return "\n".join(lines)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def rtf_to_text(rtf: str) -> str:
    """Plain text from RTF: Cyrillic comes as \\'xx (cp1251) or \\uNNNN escapes."""
    out: list[str] = []
    stack: list[bool] = []
    skip = False  # группы-служебки: шрифты, стили, картинки
    i = 0
    while i < len(rtf):
        ch = rtf[i]
        if ch == "{":
            stack.append(skip)
            if rtf.startswith("{\\*", i) or re.match(
                r"\{\\(fonttbl|colortbl|stylesheet|info|pict|header|footer)", rtf[i:]
            ):
                skip = True
            i += 1
        elif ch == "}":
            skip = stack.pop() if stack else False
            i += 1
        elif ch == "\\":
            if rtf.startswith("\\'", i):
                if not skip:
                    out.append(bytes([int(rtf[i + 2 : i + 4], 16)]).decode("cp1251", "replace"))
                i += 4
                continue
            match = re.match(r"\\([a-z]+)(-?\d+)? ?|\\(.)", rtf[i:])
            if match is None:
                i += 1
                continue
            word, arg, symbol = match.groups()
            i += match.end()
            if skip:
                continue
            if symbol:
                out.append(symbol if symbol in "\\{}" else "")
            elif word in ("par", "line", "row"):
                out.append("\n")
            elif word in ("tab", "cell"):
                out.append("\t")
            elif word == "u" and arg:
                out.append(chr(int(arg) % 65536))
                if i < len(rtf) and rtf[i] == "?":  # запасной символ после \uNNNN
                    i += 1
        else:
            if not skip and ch not in "\r\n":
                out.append(ch)
            i += 1
    return "".join(out)


def html_to_text(page: str) -> str:
    page = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h\d|tr|section)>", "\n", page)
    return html.unescape(re.sub(r"<[^>]+>", " ", page))


def _tidy(text: str) -> str:
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# --- ссылка ---


def fetch_resume_text(url: str, client: httpx.Client | None = None) -> str:
    """Resume text by link: hh.ru and other sites via Exa, Google Docs via export, else directly."""
    url = url.strip()
    if not re.match(r"https?://", url):
        raise ResumeError("Вставьте полную ссылку, начиная с https://")
    host = httpx.URL(url).host.lower()
    gdoc = re.search(r"docs\.google\.com/document/d/([\w-]+)", url)
    try:
        if gdoc:
            export = f"https://docs.google.com/document/d/{gdoc[1]}/export?format=txt"
            text = _direct(export, client)
        elif host.endswith("hh.ru") or host.endswith("headhunter.ru"):
            text = _via_exa(url, client)  # hh.ru не отдаёт страницы напрямую
        else:
            try:
                text = _direct(url, client)
            except httpx.HTTPError:
                text = ""
            if len(text) < MIN_RESUME_CHARS:
                text = _via_exa(url, client)
    except httpx.HTTPError as exc:
        raise ResumeError(f"Не удалось открыть ссылку: {exc}") from exc
    text = _tidy(text)
    if len(text) < MIN_RESUME_CHARS or _looks_closed(text):
        hint = (
            " На hh.ru откройте резюме → «Скачать» → PDF или Word и загрузите файл, либо включите "
            "видимость «Видно всему интернету»."
            if "hh.ru" in host
            else " Проверьте, что страница открывается без входа, или загрузите резюме файлом."
        )
        raise ResumeError("По ссылке не видно резюме — похоже, оно закрыто." + hint)
    return text


def _direct(url: str, client: httpx.Client | None) -> str:
    client = client or httpx.Client(timeout=30, follow_redirects=True)
    response = client.get(url, headers={"User-Agent": "Mozilla/5.0 JobMatcher"})
    response.raise_for_status()
    body = response.text
    return html_to_text(body) if "html" in response.headers.get("content-type", "") else body


def _via_exa(url: str, client: httpx.Client | None) -> str:
    api_key = get_settings().exa_api_key
    if client is None:
        if not api_key:
            raise ResumeError("Чтение ссылок hh.ru не подключено. Загрузите резюме файлом.")
        client = httpx.Client(timeout=60, headers={"x-api-key": api_key})
    response = client.post(
        "https://api.exa.ai/contents",
        json={"urls": [url], "text": {"maxCharacters": 20000}, "livecrawl": "preferred"},
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    return (results[0].get("text") or "") if results else ""


_CLOSED = re.compile(
    r"резюме (скрыто|не найдено|удалено|недоступно)|доступ к резюме ограничен|"
    r"войдите,? чтобы|авторизуйтесь",
    re.IGNORECASE,
)


def _looks_closed(text: str) -> bool:
    return bool(_CLOSED.search(text[:2000])) and len(text) < 3000


# --- анкета ---


class Job(BaseModel):
    company: str = ""
    position: str = ""
    start: str = Field(default="", description="например, 03.2019")
    end: str = Field(default="", description="пусто — по настоящее время")
    description: str = ""


class Study(BaseModel):
    institution: str = ""
    faculty: str = ""
    specialty: str = ""
    year: str = ""


class Course(BaseModel):
    name: str = ""
    organization: str = ""
    year: str = ""


class ResumeForm(BaseModel):
    """Анкета как на hh.ru. ФИО и контакты здесь не хранятся — они в подписи профиля."""

    position: str = ""
    city: str = ""
    salary: str = ""
    work_format: str = ""
    about: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[Job] = Field(default_factory=list)
    education: list[Study] = Field(default_factory=list)
    courses: list[Course] = Field(default_factory=list)
    languages: str = ""

    def is_empty(self) -> bool:
        return not any(self.model_dump().values())

    def to_text(self) -> str:
        lines = []
        if self.position:
            lines.append(f"Желаемая должность: {self.position}")
        for label, value in (
            ("Город", self.city),
            ("Зарплата", self.salary),
            ("Формат работы", self.work_format),
        ):
            if value:
                lines.append(f"{label}: {value}")
        if self.experience:
            lines.append("\nОпыт работы")
            for job in self.experience:
                period = f"{job.start or '?'} — {job.end or 'по настоящее время'}"
                lines.append(f"{period}. {job.position}, {job.company}".rstrip(", "))
                if job.description:
                    lines.append(job.description)
        if self.education:
            lines.append("\nОбразование")
            for s in self.education:
                parts = (s.year, s.institution, s.faculty, s.specialty)
                lines.append(", ".join(x for x in parts if x))
        if self.courses:
            lines.append("\nКурсы и повышение квалификации")
            for c in self.courses:
                lines.append(", ".join(x for x in (c.year, c.name, c.organization) if x))
        if self.skills:
            lines.append(f"\nКлючевые навыки: {', '.join(self.skills)}")
        if self.languages:
            lines.append(f"Языки: {self.languages}")
        if self.about:
            lines.append(f"\nО себе\n{self.about}")
        return "\n".join(lines).strip()


FORM_PROMPT = """Разложи текст резюме по полям анкеты, как на hh.ru.
Верни ТОЛЬКО JSON-объект с полями:
- position, city, salary, work_format, about, languages: строки ("" если нет)
- skills: массив ключевых навыков
- experience: массив {company, position, start, end, description} — от новых к старым;
  start/end в виде "ММ.ГГГГ", end "" если работает сейчас; description — обязанности
  и достижения из резюме, без сокращений
- education: массив {institution, faculty, specialty, year}
- courses: массив {name, organization, year}
Переноси факты как есть, ничего не выдумывай. Контакты, ФИО и дату рождения не переноси."""


def form_from_text(text: str, llm: LLM) -> ResumeForm:
    from app.profile import redact_pii

    return ResumeForm.model_validate(llm.chat_json(FORM_PROMPT, redact_pii(text)))


# --- хранение ---


class ResumeSource(BaseModel):
    kind: Literal["file", "link", "form"]
    name: str = Field(default="", description="имя файла или адрес ссылки")
    updated_at: datetime
    chars: int = 0


class ResumeStore:
    """Files next to the resume: resume.txt (text), resume_source.json, resume_form.json."""

    def __init__(self, resume_path: Path) -> None:
        self.legacy = resume_path  # data/resume.pdf — так резюме клали до загрузки с сайта
        self.text_path = resume_path.with_suffix(".txt")
        self.source_path = resume_path.with_name("resume_source.json")
        self.form_path = resume_path.with_name("resume_form.json")

    def text(self) -> str:
        if self.text_path.exists():
            return self.text_path.read_text(encoding="utf-8")
        if self.legacy.exists():
            return extract_text(self.legacy.read_bytes(), self.legacy.name)
        return ""

    def source(self) -> ResumeSource | None:
        if self.source_path.exists():
            return ResumeSource.model_validate_json(self.source_path.read_text(encoding="utf-8"))
        if self.legacy.exists():
            stat = self.legacy.stat()
            return ResumeSource(
                kind="file",
                name=self.legacy.name,
                updated_at=datetime.fromtimestamp(stat.st_mtime, UTC),
            )
        return None

    def save_text(self, text: str, kind: str, name: str) -> ResumeSource:
        self.text_path.parent.mkdir(parents=True, exist_ok=True)
        self.text_path.write_text(text, encoding="utf-8")
        source = ResumeSource(kind=kind, name=name, updated_at=datetime.now(UTC), chars=len(text))
        self.source_path.write_text(source.model_dump_json(indent=2), encoding="utf-8")
        return source

    def form(self) -> ResumeForm | None:
        if not self.form_path.exists():
            return None
        return ResumeForm.model_validate_json(self.form_path.read_text(encoding="utf-8"))

    def save_form(self, form: ResumeForm) -> None:
        self.form_path.parent.mkdir(parents=True, exist_ok=True)
        self.form_path.write_text(
            json.dumps(form.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
