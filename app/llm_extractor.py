"""Извлечение фактов из протокола локальной LLM (Qwen3-8B через Ollama).

Модуль отвечает только на вопрос «что фактически написано в протоколе».
Он НЕ ставит диагноз, НЕ назначает лечение, НЕ выбирает врача и НЕ строит маршрут —
это по-прежнему делает детерминированный processor.py c rules/*.json.

Работает в shadow-режиме: результат сохраняется рядом с rule-based, но не влияет
на маршрут. При недоступности Ollama работа продолжается на правилах.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from typing import Any

from pydantic import BaseModel, Field, ValidationError

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:8b"


# ── Схема ответа модели ─────────────────────────────────────────────────────

class ExtractedFinding(BaseModel):
    name: str = Field(description="Название находки, как написано")
    status: str = Field(description="present | negated | uncertain")
    evidence: str = Field(description="Точная цитата из исходного текста")
    location: str | None = None
    laterality: str | None = None  # right | left | bilateral | null
    size_mm: float | None = None
    birads: int | None = None
    tirads: int | None = None
    orads: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ProtocolFacts(BaseModel):
    study_type: str | None = None
    organ: str | None = None
    findings: list[ExtractedFinding] = Field(default_factory=list)


SYSTEM_PROMPT = """Ты — модуль извлечения фактов из медицинского протокола.
Твоя задача — не интерпретировать тактику, а извлекать только явно написанные факты.

Запрещено:
- ставить диагноз от себя;
- придумывать отсутствующие факты;
- выбирать специалиста;
- назначать обследование или лечение;
- делать клинические рекомендации.

Для каждой находки обязательно верни точную цитату evidence из исходного текста.

Статусы:
present — находка явно утверждается;
negated — находка явно отрицается («не выявлено», «нет», «не обнаружено»);
uncertain — формулировка содержит неопределённость («нельзя исключить», «возможно»,
«вероятно», «под вопросом», «может соответствовать»).

Если в тексте прямо указаны размеры, сторона или категории — заполни поля:
size_mm (число в миллиметрах), laterality (right/left/bilateral),
birads (число 1-5), tirads (число), orads (число). Если чего-то нет — оставь null,
не придумывай.

Если факт отсутствует — не придумывай его. Ответ строго по JSON-схеме."""


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def llm_enabled() -> bool:
    return _env("USE_LLM", "false").lower() in ("1", "true", "yes", "on")


def llm_mode() -> str:
    return _env("LLM_MODE", "shadow").lower()


def _host() -> str:
    return _env("OLLAMA_HOST", DEFAULT_HOST).rstrip("/")


def _model() -> str:
    return _env("OLLAMA_MODEL", DEFAULT_MODEL)


def _timeout() -> float:
    try:
        return float(_env("LLM_TIMEOUT_SECONDS", "30"))
    except ValueError:
        return 30.0


# ── Проверка evidence ───────────────────────────────────────────────────────

def _norm_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\u00a0", " ")).strip().lower()


def evidence_is_valid(evidence: str, source: str) -> bool:
    """Evidence должна реально встречаться в исходном протоколе."""
    if not evidence:
        return False
    return _norm_spaces(evidence) in _norm_spaces(source)


# ── Вызов Ollama ────────────────────────────────────────────────────────────

def _call_ollama(text: str) -> tuple[dict, float]:
    payload = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "stream": False,
        "format": ProtocolFacts.model_json_schema(),
        "think": _env("OLLAMA_THINK", "false").lower() in ("1", "true", "yes", "on"),
        "options": {"temperature": 0},
    }
    req = urllib.request.Request(
        _host() + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=_timeout()) as resp:
        data = json.load(resp)
    latency = (time.time() - started) * 1000
    content = (data.get("message") or {}).get("content", "")
    return json.loads(content), latency


def extract_facts_llm(text: str, protocol_id: str = "") -> dict:
    """Возвращает структурированные факты. Бросает исключение при ошибке —
    вызывающая сторона обязана продолжить работу на правилах."""
    raw, latency = _call_ollama(text)
    try:
        facts = ProtocolFacts.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"LLM вернула некорректный JSON: {exc}") from exc

    findings = []
    invalid = 0
    for f in facts.findings:
        item = f.model_dump()
        item["evidence_valid"] = evidence_is_valid(f.evidence, text)
        if not item["evidence_valid"]:
            item["flag"] = "invalid_evidence"
            invalid += 1
        findings.append(item)

    return {
        "study_type": facts.study_type,
        "organ": facts.organ,
        "findings": findings,
        "findings_count": len(findings),
        "invalid_evidence": invalid,
        "latency_ms": round(latency),
        "model": _model(),
        "protocol_id": protocol_id,
    }


def shadow_result(text: str, protocol_id: str = "") -> dict:
    """Безопасная обёртка для shadow-режима: никогда не поднимает исключение."""
    if not llm_enabled() or llm_mode() == "off":
        return {"enabled": False, "mode": llm_mode(), "model": _model()}
    try:
        facts = extract_facts_llm(text, protocol_id)
        # Логируем только технические метрики, без ПДн и текста протокола.
        print(
            f"LLM extraction: protocol_id={protocol_id} model={facts['model']} "
            f"latency_ms={facts['latency_ms']} findings={facts['findings_count']} status=success"
        )
        return {"enabled": True, "mode": "shadow", **facts, "error": None}
    except Exception as exc:  # noqa: BLE001 — любой сбой не должен ломать систему
        print(
            f"LLM extraction: protocol_id={protocol_id} model={_model()} "
            f"status=error error={type(exc).__name__}"
        )
        return {"enabled": True, "mode": "shadow", "model": _model(), "facts": None, "error": str(exc)}


def health() -> dict:
    """Диагностика без вывода медицинского текста."""
    info = {
        "enabled": llm_enabled(),
        "mode": llm_mode(),
        "available": False,
        "model": _model(),
        "host": _host(),
    }
    if not llm_enabled():
        return info
    try:
        req = urllib.request.Request(_host() + "/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
        names = [m.get("name", "") for m in data.get("models", [])]
        info["available"] = any(_model().split(":")[0] in n for n in names)
        if not info["available"]:
            info["error"] = f"модель {_model()} не найдена в Ollama"
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info
