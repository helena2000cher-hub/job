"""LLM access through polza.ai — an OpenAI-compatible aggregator (Claude, DeepSeek, Qwen, ...).

Everything that talks to a model goes through the `LLM` protocol, so tests can pass a fake.
"""

import json
import logging
import re
from typing import Any, Protocol

from openai import OpenAI

from app.config import get_settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    def chat_json(self, system: str, user: str, *, smart: bool = False) -> dict[str, Any]: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class PolzaLLM:
    def __init__(self, client: OpenAI | None = None) -> None:
        settings = get_settings()
        if client is None and not settings.polza_api_key:
            raise LLMError("POLZA_API_KEY не задан в .env")
        self._client = client or OpenAI(
            api_key=settings.polza_api_key, base_url=settings.polza_base_url, timeout=120
        )
        self._fast = settings.llm_model_fast
        self._smart = settings.llm_model_smart
        self._embedding_model = settings.embedding_model

    def chat_json(self, system: str, user: str, *, smart: bool = False) -> dict[str, Any]:
        """Ask the model for a JSON object; one retry if the answer is not valid JSON."""
        model = self._smart if smart else self._fast
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for attempt in (1, 2):
            response = self._client.chat.completions.create(
                model=model, messages=messages, temperature=0, max_tokens=4000
            )
            content = response.choices[0].message.content or ""
            try:
                return extract_json(content)
            except ValueError:
                log.warning("%s returned invalid JSON (attempt %d)", model, attempt)
                messages += [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": "Ответ не является валидным JSON. Верни только JSON.",
                    },
                ]
        raise LLMError(f"{model} не вернула валидный JSON")

    def embed(self, texts: list[str]) -> list[list[float]]:
        # polza.ai принимает в /embeddings только строки (не токены) — SDK так и отправляет.
        response = self._client.embeddings.create(model=self._embedding_model, input=texts)
        return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from a model answer, tolerating ```json fences and surrounding text."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model answer")
    try:
        data = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(data, dict):
        raise ValueError("JSON is not an object")
    return data
