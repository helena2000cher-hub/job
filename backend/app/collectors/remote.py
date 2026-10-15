import re

# Только явные формулировки удалёнки: просто «удалённый» ловит «удалённых районов».
_WORK = r"(?:работ|формат|режим|занятост|основ)"
_REMOTE = re.compile(
    rf"удал[её]нн\w*\s+{_WORK}|удал[её]нно\b|дистанционн\w*\s+{_WORK}|из дома|\bremote\b",
    re.IGNORECASE,
)
_NOT_REMOTE = re.compile(
    r"(?:не|без)\s+(?:\w+\s+)?(?:удал[её]нн|дистанционн)|удал[её]нн\w*\s+(?:работ\w*\s+)?нет",
    re.IGNORECASE,
)
_REMOTE_EMPLOYMENT = re.compile(r"удал[её]нн|дистанционн", re.IGNORECASE)


def detect_remote(employment: str | None, text: str) -> bool:
    """Remote if the source flags it in employment type, or the text clearly says so."""
    if employment and _REMOTE_EMPLOYMENT.search(employment):
        return True
    return bool(_REMOTE.search(text)) and not _NOT_REMOTE.search(text)
