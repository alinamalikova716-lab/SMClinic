"""Ядро решения: извлечение клинически значимых триггеров из текста протокола
и определение маршрута пациента.

Разделение ответственности (как рекомендует кейс):
  1) extraction  — что найдено в тексте (со ссылкой на фрагмент-доказательство);
  2) routing     — что с этим делать (детерминированные правила по матрице).

Статусы находки:
  trigger   — находка подтверждена  -> создаёт маршрут;
  uncertain — реально противоречивая формулировка («нельзя исключить») ->
              маршрут НЕ создаётся автоматически, уходит в очередь «Требует уточнения»;
  negated   — находка отрицается    -> маршрута нет.

Правила лежат в rules/*.json и являются настройками, а не хардкодом.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.path.join(HERE, "rules")

NEGATION_CUES = [
    "не выявлен", "не выявляется", "не определяется", "не определяются",
    "не обнаружен", "не лоциру", "не визуализир",
    "не изменен", "не утолщен", "не расширен", "не деформирован",
    "не увеличен", "не увеличена", "не увеличены", "не подтвержд",
    "не отмеч", "не характерн", "не нарушен", "не зафиксирован",
    "без признак", "без образован", "без изменен", "без особенност",
    "без патологии", "без стеноз", "без смещен", "отсутств",
    "нет данных", "не получено", "нет ",
]

# Дисклеймеры и «хвосты» заключений. Их надо убрать ДО разбора: фразы вида
# «данное заключение не является диагнозом» иначе дают ложное отрицание
# найденной рядом патологии.
BOILERPLATE_MARKERS = [
    "не является диагнозом",
    "не является клиническим диагнозом",
    "не является окончательным",
    "не является диагнозом",
    "сохраняйте протокол",
    "предъявляйте врач",
    "интерпретир",
    "требует интерпретации",
    "для интерпретации",
    "уважаемые пациенты",
    "важная информация",
    "бесплатную онлайн",
    "мнение профильного",
    "пациент имеет возможность",
]

# Приоритет статуса при слиянии повторов одной находки.
STATUS_PRIORITY = {"trigger": 0, "uncertain": 1, "negated": 2}

SENT_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n+")
CLAUSE_SPLIT = re.compile(r"[,;:()\-–—]|\n+")
PARA_SPLIT = re.compile(r"\n\s*\n")


def _norm(text: str) -> str:
    """Нормализация без смещения индексов (длина сохраняется)."""
    out = text.replace("\u00a0", " ").replace("ё", "е").replace("Ё", "Е")
    return out.lower()


def _strip_boilerplate(text: str) -> str:
    """Вырезает только сам дисклеймер, не трогая находки.

    Находка и дисклеймер часто склеены без пробела/точки
    («...конкрементов желчного пузыря.Заключение не является диагнозом»),
    поэтому нельзя выбрасывать предложение целиком — иначе теряется находка.
    Режем от маркера до конца предложения: текст ДО маркера сохраняется.
    """
    cleaned = text
    for m in BOILERPLATE_MARKERS:
        cleaned = re.sub(rf"{re.escape(m)}[^.!?\n]*[.!?]?", " ", cleaned, flags=re.I)
    return cleaned


def sentences(norm_text: str) -> list[tuple[int, int]]:
    """Границы предложений. Строим через finditer, чтобы покрытие было без «дыр»."""
    spans: list[tuple[int, int]] = []
    start = 0
    for m in SENT_SPLIT.finditer(norm_text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(norm_text)))
    return [(a, b) for a, b in spans if b > a]


def _spans(norm_text: str, splitter: re.Pattern) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for m in splitter.finditer(norm_text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(norm_text)))
    return [(a, b) for a, b in spans if b > a]


def _enclosing(spans: list[tuple[int, int]], pos: int) -> tuple[int, int] | None:
    for a, b in spans:
        if a <= pos < b:
            return a, b
    return None


_norm_cache = ""


def _sentence_of(spans: list[tuple[int, int]], start: int) -> str:
    for a, b in spans:
        if a <= start < b:
            return _norm_cache[a:b]
    return ""


@dataclass
class Finding:
    id: str
    title: str
    domain: str
    severity: str
    status: str  # trigger | uncertain | negated
    confidence: float
    evidence: str
    match: str
    attributes: dict[str, Any] = field(default_factory=dict)
    marker: str = ""  # маркер формулировки (информативно)
    rule_version: str = ""
    in_conclusion: bool = True  # найдено ли в заключении
    issue: str = ""  # причина пометки «требует уточнения»

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("in_conclusion", None)
        return d


def load_rules() -> tuple[dict, dict, dict]:
    with open(os.path.join(RULES, "triggers.json"), encoding="utf-8") as fh:
        triggers = json.load(fh)
    with open(os.path.join(RULES, "routing.json"), encoding="utf-8") as fh:
        routing = json.load(fh)
    with open(os.path.join(RULES, "uncertainty.json"), encoding="utf-8") as fh:
        uncertainty = json.load(fh)
    return triggers, routing, uncertainty


def _uncertainty_markers(uncertainty: dict) -> list[str]:
    markers = list(uncertainty.get("strong", []))
    if uncertainty.get("weak_enabled"):
        markers += list(uncertainty.get("weak", []))
    return [_norm(m) for m in markers]


ZAKL_RE = re.compile(r"заключени[ея]", re.I)

# Обороты, которые НЕ являются заголовком заключения (дисклеймеры и хвосты).
_NOT_A_HEADER = ("данное заключение", "заключение не является", "заключение является",
                 "заключение носит", "результаты узи", "результаты ультразвукового")


def _conclusion_start(norm_text: str) -> int | None:
    """Позиция начала содержательного заключения (последний настоящий заголовок)
    или None, если заключения в протоколе нет."""
    best = None
    for m in ZAKL_RE.finditer(norm_text):
        head = norm_text[m.start(): m.start() + 60]
        if "не является" in head or "не являются" in head:
            continue
        if any(head.startswith(b) for b in _NOT_A_HEADER):
            continue
        best = m.start()
    return best


def _extract_attributes(window: str, wanted: list[str]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if "size" in wanted:
        m = re.search(r"\d+[.,]?\d*\s*(?:х|x|\*)\s*\d+[.,]?\d*(?:\s*(?:х|x|\*)\s*\d+[.,]?\d*)?\s*мм", window)
        if m:
            attrs["size"] = m.group(0).strip()
        else:
            m = re.search(r"до\s*\d+[.,]?\d*\s*мм", window)
            if m:
                attrs["size"] = m.group(0).strip()
    if "endometrium_thickness" in wanted:
        m = re.search(r"эндометрия[:\s]+(\d+[.,]?\d*)\s*мм", window)
        if m:
            attrs["endometrium_thickness_mm"] = m.group(1)
    if "birads" in wanted:
        m = re.search(r"bi[\s-]?rads[^0-9]{0,15}(\d)", window)
        if m:
            attrs["birads"] = int(m.group(1))
    if "tirads" in wanted:
        m = re.search(r"ti[\s-]?rads[^0-9]{0,15}(\d)", window)
        if m:
            attrs["tirads"] = int(m.group(1))
    if "count" in wanted:
        if "множественн" in window:
            attrs["count"] = "множественные"
        elif "единичн" in window:
            attrs["count"] = "единичный"
    return attrs


def _make_quote(text: str, sa: int, sb: int, start: int, end: int, max_len: int = 320) -> str:
    """Цитата = целое предложение с находкой. Не режем по символам,
    чтобы не рвать слова; длинное предложение обрезаем по границам слов."""
    quote = text[sa:sb].strip()
    if len(quote) <= max_len:
        return quote
    rel = start - sa  # позиция находки внутри предложения
    half = max_len // 2
    left = max(0, rel - half)
    right = min(len(quote), left + max_len)
    left = max(0, right - max_len)
    frag = quote[left:right]
    if left > 0:
        sp = frag.find(" ")
        frag = ("…" + frag[sp + 1:]) if sp != -1 else "…" + frag
    if right < len(quote):
        sp = frag.rfind(" ")
        frag = (frag[:sp] + "…") if sp != -1 else frag + "…"
    return frag.strip()


def _base(token: str) -> str:
    t = token.lower().strip()
    return t[: max(4, len(t) - 2)] if len(t) > 5 else t


def _mentioned(finding: Finding, patterns: list, conclusion: str) -> bool:
    """Упомянута ли находка в заключении — по основе слова, без точного совпадения."""
    if _base(finding.match) and _base(finding.match) in conclusion:
        return True
    for p in patterns:
        if isinstance(p, dict):
            p = p.get("text") or ""
        if not p or not isinstance(p, str):
            continue
        b = _base(p)
        if b and b in conclusion:
            return True
    return False


# Находки, которые считаются «дополнительными изменениями»: если они есть
# в описании, но не упомянуты в заключении — протокол идёт в «Требует уточнения».
EXTRA_FINDINGS = {"lymphadenopathy", "pelvic_varicose", "ovarian_enlargement", "biliary_dyskinesia"}


def _guard_value(window: str, kind: str | None) -> int | None:
    """Числовое значение для проверки условия (например, категория BI-RADS)."""
    if kind == "birads":
        m = re.search(r"bi[\s-]?rads[^0-9]{0,15}(\d)", window)
        return int(m.group(1)) if m else None
    if kind == "tirads":
        m = re.search(r"ti[\s-]?rads[^0-9]{0,15}(\d)", window)
        return int(m.group(1)) if m else None
    return None


def extract(text: str, triggers: dict, uncertainty: dict) -> list[Finding]:
    global _norm_cache
    text = _strip_boilerplate(text)
    norm = _norm(text)
    _norm_cache = norm
    sents = sentences(norm)
    concl_start = _conclusion_start(norm)
    has_concl = concl_start is not None
    has_concl_trigger = False
    markers = _uncertainty_markers(uncertainty)
    rule_patterns = {r["id"]: r.get("patterns", []) for r in triggers["findings"]}
    results: list[Finding] = []

    for rule in triggers["findings"]:
        for pattern in rule["patterns"]:
            guard = None
            if isinstance(pattern, dict) and "regex" in pattern:
                regex = pattern["regex"]
                guard = pattern.get("guard")
            elif isinstance(pattern, dict):
                regex = re.escape(_norm(pattern.get("text", "")))
                guard = pattern.get("guard")
            else:
                regex = re.escape(_norm(pattern))
            for m in re.finditer(regex, norm):
                start, end = m.start(), m.end()
                # границы предложения: отрицание/неопределённость ищем только внутри
                sent_span = _enclosing(sents, start)
                if sent_span is None:
                    continue
                sa, sb = sent_span

                # require_context: контекстное слово рядом (окно настраивается правилом)
                req = rule.get("require_context")
                if req:
                    cw = rule.get("context_window", 200)
                    cwindow = norm[max(0, start - cw): min(len(norm), end + cw)]
                    if not any(_norm(w) in cwindow for w in req):
                        continue

                # exclude_context: обороты, при которых совпадение не является
                # патологией (например, «нестенозирующий атеросклероз»).
                exc = rule.get("exclude_context")
                if exc:
                    ew = rule.get("exclude_window", 30)
                    ewindow = norm[max(0, start - ew): min(len(norm), end + ew)]
                    if any(_norm(w) in ewindow for w in exc):
                        continue

                # отрицание/неопределённость и атрибуты — внутри предложения
                lo = max(sa, start - 80)
                hi = min(sb, end + 80)
                window = norm[lo:hi]

                # числовое условие паттерна (например, BI-RADS только 3-5)
                if guard:
                    val = _guard_value(window, guard.get("kind"))
                    if val is not None and val < guard.get("min", 0):
                        continue

                # «нельзя исключить <патологию>» — это ЯВНЫЙ ТРИГГЕР (врач поставит диагноз),
                # поэтому маркер неопределённости больше не переводит находку в «уточнение».
                marker = next((mk for mk in markers if mk in window), "")
                exceptions = [_norm(e) for e in uncertainty.get("negation_exceptions", [])]
                excepted = any(e in window for e in exceptions)

                # отрицание: обороты «не выявлено/без признаков…» + «без <патологии>» перед находкой
                before = norm[max(sa, start - 25):start]
                negated = any(cue in window for cue in NEGATION_CUES) or ("без" in before)

                if not excepted and negated:
                    status, confidence = "negated", 0.55
                else:
                    status, confidence = "trigger", 0.9

                in_concl = bool(has_concl) and start >= concl_start
                if in_concl:
                    has_concl_trigger = True

                results.append(
                    Finding(
                        id=rule["id"],
                        title=rule["title"],
                        domain=rule["domain"],
                        severity=rule["severity"],
                        status=status,
                        confidence=confidence,
                        evidence=_make_quote(text, sa, sb, start, end),
                        match=text[start:end],
                        attributes=_extract_attributes(window, rule.get("attributes", [])),
                        marker=marker,
                        rule_version=triggers["version"],
                        in_conclusion=in_concl,
                    )
                )

    # Находка описана в протоколе, но отсутствует в заключении —
    # вероятна ошибка автора протокола. Маршрут (и пуш) всё равно создаём,
    # но помечаем для координатора в разделе «Требует уточнения».
    # Если заключение не распознано, но в тексте есть рекомендация специалиста —
    # это не повод для «уточнения» (протокол понятный). Поэтому здесь ничего не помечаем.

    return results


def dedupe(findings: list[Finding]) -> list[Finding]:
    """Одна находка могла встретиться несколько раз с разными статусами.
    Приоритет: подтверждено > неопределённо > отрицается."""
    best: dict[str, Finding] = {}
    for f in findings:
        cur = best.get(f.id)
        if cur is None:
            best[f.id] = f
            continue
        if STATUS_PRIORITY[f.status] < STATUS_PRIORITY[cur.status]:
            best[f.id] = f
        elif f.status == cur.status and f.confidence > cur.confidence:
            best[f.id] = f
    return list(best.values())


def route(findings: list[Finding], routing: dict) -> list[dict]:
    out = []
    for f in findings:
        if f.status not in ("trigger", "uncertain"):
            continue
        r = routing["routes"].get(f.id, routing["default"])
        out.append({"finding_id": f.id, "title": f.title, **r})
    # срочные — первыми
    order = {"emergency": 0, "urgent": 1, "planned": 2, "watch": 3}
    out.sort(key=lambda x: order.get(x.get("priority", "planned"), 9))
    return out


def _suggested_route(f: Finding, routing: dict) -> dict:
    r = routing["routes"].get(f.id, routing["default"])
    return {"finding_id": f.id, "title": f.title, **r}


def process(text: str, triggers: dict, routing: dict, uncertainty: dict) -> dict:
    raw = extract(text, triggers, uncertainty)
    findings = dedupe(raw)
    triggers_found = [f for f in findings if f.status in ("trigger", "uncertain")]
    uncertain = [f for f in findings if f.status == "uncertain"]

    reviews = [
        {
            "finding": f.to_dict(),
            "suggested_route": _suggested_route(f, routing),
        }
        for f in uncertain
    ]

    return {
        "findings": [f.to_dict() for f in findings],
        "triggers": [f.to_dict() for f in triggers_found],
        "uncertain": [f.to_dict() for f in uncertain],
        "routes": route(findings, routing),
        "reviews": reviews,
        "is_trigger": bool(triggers_found),
    }
