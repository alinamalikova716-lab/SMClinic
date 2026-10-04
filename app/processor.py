"""Ядро решения: извлечение клинически значимых триггеров из текста протокола
и определение маршрута пациента.

Разделение ответственности (как рекомендует кейс):
  1) extraction  — что найдено в тексте (со ссылкой на фрагмент-доказательство);
  2) routing     — что с этим делать (детерминированные правила по матрице).

Статусы находки:
  trigger  — находка подтверждена -> создаёт маршрут;
  negated  — находка отрицается  -> маршрута нет.

Решение по формулировкам «нельзя исключить / подозрение на» (п. 1.5 ТЗ):
они считаются ЯВНЫМ ТРИГГЕРОМ — врач на приёме поставит диагноз.
Статус `uncertain` из логики выведен; раздел «Требует уточнения» оставлен
для будущих сценариев (протоколы без заключения и без рекомендаций).

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

# ── Отрицания ───────────────────────────────────────────────────────────────
# Только осмысленные обороты. Голое «нет » убрано (п. 1.3) — заменено
# регексом NO_FINDING_RE, который требует существительное-мишень.
NEGATION_CUES = [
    "не выявлен", "не выявляется", "не определяется", "не определяются",
    "не обнаружен", "не лоциру", "не визуализир",
    "не изменен", "не утолщен", "не расширен", "не деформирован",
    "не увеличен", "не увеличена", "не увеличены", "не подтвержд",
    "не отмеч", "не характерн", "не нарушен", "не зафиксирован",
    "без признак", "без образован", "без изменен", "без особенност",
    "без патологии", "без стеноз", "без смещен", "отсутств",
    "нет данных", "не получено",
]

# «нет <патологии>» — только с существительным-мишенью.
NO_FINDING_RE = re.compile(
    r"\bнет\s+(признак|данных|образован|узл|кист|конкремент|патолог|"
    r"изменен|атеросклеротическ)"
)

# Дисклеймеры и «хвосты» заключений — вырезаем до конца строки (п. 2.5).
BOILERPLATE_MARKERS = [
    "не является диагнозом",
    "не является клиническим диагнозом",
    "не является окончательным",
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

STATUS_PRIORITY = {"trigger": 0, "uncertain": 1, "negated": 2}

# Признаки того, что протокол «понятный»: есть рекомендация/наблюдение.
RECOMMENDATION_RE = re.compile(r"рекомендован|консультац|наблюдени|направлен|контроль|дообследован")

# Границы предложений: точка/!/? + пробел, либо перенос строки (п. 2.1).
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
# Клаузы: запятая, точка с запятой, двоеточие, тире, перенос строки (п. 1.4).
CLAUSE_SPLIT = re.compile(r"[,;:—–]|\n+")

# Маркеры сторон для определения латеральности (п. 1.1).
_RIGHT_MARKERS = ["правая молочная", "правая доля", "правый яичник", "правое яичко",
                  "справа", "правая", "правой", "правого", "правым", "правый"]
_LEFT_MARKERS = ["левая молочная", "левая доля", "левый яичник", "левое яичко",
                 "слева", "левая", "левой", "левого", "левым", "левый"]


def _norm(text: str) -> str:
    """Нормализация без смещения индексов (длина сохраняется)."""
    out = text.replace("\u00a0", " ").replace("ё", "е").replace("Ё", "Е")
    return out.lower()


def _strip_boilerplate(text: str) -> str:
    """Вырезает дисклеймер до конца строки (точку не трогаем — п. 2.5)."""
    cleaned = text
    for m in BOILERPLATE_MARKERS:
        cleaned = re.sub(rf"{re.escape(m)}[^\n]*", " ", cleaned, flags=re.I)
    return cleaned


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


@dataclass
class Finding:
    id: str
    title: str
    domain: str
    severity: str
    status: str  # trigger | negated
    confidence: float
    evidence: str
    match: str
    attributes: dict[str, Any] = field(default_factory=dict)
    marker: str = ""
    negation_cue: str = ""  # какая фраза погасила находку (п. 3.3)
    rule_version: str = ""
    in_conclusion: bool = False
    issue: str = ""

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


# ── Определение сторон и заключения ─────────────────────────────────────────

def _section_of(norm_text: str, pos: int) -> str:
    """right / left / unknown — по последней шапке секции перед находкой (п. 1.1)."""
    r = max((norm_text.rfind(m, 0, pos) for m in _RIGHT_MARKERS), default=-1)
    l = max((norm_text.rfind(m, 0, pos) for m in _LEFT_MARKERS), default=-1)
    if r < 0 and l < 0:
        return "unknown"
    if r > l:
        return "right"
    if l > r:
        return "left"
    return "unknown"


_ZAKL_WORD = re.compile(r"заключени[ея]", re.I)
# Заголовок заключения: слово + двоеточие/тире/перенос, либо «ЗАКЛЮЧЕНИЕ ИССЛЕДОВАНИЯ».
_ZAKL_HEADER = re.compile(r"заключени[ея]\s*(?:исследования)?\s*[:\-—–\n]|^\s*заключени[ея]\s*$", re.I | re.M)
_NOT_A_HEADER = ("данное заключение", "заключение не является", "заключение является",
                 "заключение носит", "результаты узи", "результаты ультразвукового")


def _conclusion_start(norm_text: str) -> int | None:
    """Позиция заголовка содержательного заключения (последнего) или None (п. 2.2)."""
    best = None
    for m in _ZAKL_HEADER.finditer(norm_text):
        head = norm_text[m.start(): m.start() + 60]
        if "не является" in head or "не являются" in head:
            continue
        if any(head.startswith(b) for b in _NOT_A_HEADER):
            continue
        best = m.start()
    return best


# ── Атрибуты ────────────────────────────────────────────────────────────────

def _extract_attributes(window: str, wanted: list[str]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if "size" in wanted:
        m = re.search(r"\d+[.,]?\d*\s*(?:х|x|\*)\s*\d+[.,]?\d*(?:\s*(?:х|x|\*)\s*\d+[.,]?\d*)?\s*мм", window)
        if not m:
            m = re.search(r"до\s*\d+[.,]?\d*\s*мм", window)
        if not m:
            m = re.search(r"\d+[.,]?\d*\s*мм", window)  # одиночный размер (п. 2.4)
        if m:
            attrs["size"] = m.group(0).strip()
    if "endometrium_thickness" in wanted:
        m = re.search(r"эндометрия[:\s]+(\d+[.,]?\d*)\s*мм", window)
        if m:
            attrs["endometrium_thickness_mm"] = m.group(1)
    if "birads" in wanted:
        vals = re.findall(r"bi[\s-]?rads[^0-9]{0,15}(\d)", window)
        if vals:
            attrs["birads"] = sorted({int(v) for v in vals})
    if "tirads" in wanted:
        vals = re.findall(r"ti[\s-]?rads[^0-9]{0,15}(\d)", window)
        if vals:
            attrs["tirads"] = sorted({int(v) for v in vals})
    if "count" in wanted:
        if "множественн" in window:
            attrs["count"] = "множественные"
        elif "единичн" in window:
            attrs["count"] = "единичный"
    return attrs


def _make_quote(text: str, sa: int, sb: int, start: int, end: int, max_len: int = 320) -> str:
    quote = text[sa:sb].strip()
    if len(quote) <= max_len:
        return quote
    rel = start - sa
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


def _guard_value(window: str, kind: str | None) -> int | None:
    if kind == "birads":
        m = re.search(r"bi[\s-]?rads[^0-9]{0,15}(\d)", window)
        return int(m.group(1)) if m else None
    if kind == "tirads":
        m = re.search(r"ti[\s-]?rads[^0-9]{0,15}(\d)", window)
        return int(m.group(1)) if m else None
    return None


# ── Извлечение ──────────────────────────────────────────────────────────────

def extract(text: str, triggers: dict, uncertainty: dict) -> list[Finding]:
    text = _strip_boilerplate(text)
    norm = _norm(text)
    sents = _spans(norm, SENT_SPLIT)
    clauses = _spans(norm, CLAUSE_SPLIT)
    concl_start = _conclusion_start(norm)
    has_concl = concl_start is not None

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
                sent_span = _enclosing(sents, start)
                if sent_span is None:
                    continue
                sa, sb = sent_span

                # require_context — орган рядом (окно настраивается правилом)
                req = rule.get("require_context")
                if req:
                    cw = rule.get("context_window", 200)
                    cwindow = norm[max(0, start - cw): min(len(norm), end + cw)]
                    if not any(_norm(w) in cwindow for w in req):
                        continue

                # exclude_context — обороты, которые не являются патологией
                exc = rule.get("exclude_context")
                if exc:
                    ew = rule.get("exclude_window", 30)
                    ewindow = norm[max(0, start - ew): min(len(norm), end + ew)]
                    if any(_norm(w) in ewindow for w in exc):
                        continue

                # клауза находки — окно для негации (п. 1.4)
                clause = _enclosing(clauses, start)
                if clause and clause[1] - clause[0] >= 15:
                    lo, hi = clause
                else:
                    lo, hi = sa, sb  # слишком короткая клауза — берём предложение
                window = norm[lo:hi]

                # числовое условие паттерна: min/max (п. 2.3)
                if guard:
                    val = _guard_value(window, guard.get("kind"))
                    if val is not None and (val < guard.get("min", 0) or val > guard.get("max", 99)):
                        continue

                exceptions = [_norm(e) for e in uncertainty.get("negation_exceptions", [])]
                excepted = any(e in window for e in exceptions)

                cue = next((c for c in NEGATION_CUES if c in window), "")
                no_finding = NO_FINDING_RE.search(window)
                negated = bool(cue) or bool(no_finding)

                if not excepted and negated:
                    status, confidence = "negated", 0.55
                else:
                    status, confidence = "trigger", 0.9
                    cue = ""

                in_concl = bool(has_concl) and start >= concl_start

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
                        attributes={
                            **_extract_attributes(window, rule.get("attributes", [])),
                            "laterality": _section_of(norm, start),
                        },
                        marker="",
                        negation_cue=cue or (no_finding.group(0) if no_finding else ""),
                        rule_version=triggers["version"],
                        in_conclusion=in_concl,
                    )
                )

    # «Требует уточнения» — «непонятный» протокол: есть находка, но заключение
    # не распознано И нет рекомендации специалиста. Тогда протокол помечаем
    # для проверки (маршрут и уведомление при этом всё равно создаются).
    if results and not has_concl and not RECOMMENDATION_RE.search(norm):
        for f in results:
            if f.status != "negated":
                f.status = "uncertain"
                f.issue = "Заключение не распознано, рекомендация врача отсутствует — протокол требует проверки"

    return results


def _merge_attributes(a: dict, b: dict) -> dict:
    merged = dict(a)
    for k, v in b.items():
        if k in merged and merged[k] != v:
            merged.setdefault("_alt", {})[k] = v
        else:
            merged[k] = v
    return merged


def dedupe(findings: list[Finding]) -> list[Finding]:
    """Слияние повторов по (id, laterality) — двусторонние находки не схлопываются (п. 1.1)."""
    best: dict[str, Finding] = {}
    for f in findings:
        key = f"{f.id}|{f.attributes.get('laterality', 'unknown')}"
        cur = best.get(key)
        if cur is None:
            best[key] = f
            continue
        if STATUS_PRIORITY[f.status] < STATUS_PRIORITY[cur.status]:
            f.attributes = _merge_attributes(cur.attributes, f.attributes)
            best[key] = f
        elif f.status == cur.status and f.confidence > cur.confidence:
            f.attributes = _merge_attributes(cur.attributes, f.attributes)
            best[key] = f
        else:
            cur.attributes = _merge_attributes(cur.attributes, f.attributes)
    return list(best.values())


def route(findings: list[Finding], routing: dict) -> list[dict]:
    order = {"emergency": 0, "urgent": 1, "planned": 2, "watch": 3}
    out = []
    for f in findings:
        if f.status not in ("trigger", "uncertain"):
            continue
        r = dict(routing["routes"].get(f.id, routing["default"]))
        # BI-RADS/TI-RADS: берём максимальную категорию (п. 1.2)
        for key in ("birads", "tirads"):
            vals = f.attributes.get(key)
            if vals is None:
                continue
            vals = vals if isinstance(vals, list) else [vals]
            if vals and max(vals) >= 4:
                r["priority"] = "urgent"
                r["target_days"] = min(int(r.get("target_days", 3)), 3)
                r["priority_reason"] = (r.get("priority_reason", "") + f" ({key.upper()} ≥4)").strip()
        out.append({"finding_id": f.id, "title": f.title, **r})
    out.sort(key=lambda x: order.get(x.get("priority", "planned"), 9))
    return out


def _suggested_route(f: Finding, routing: dict) -> dict:
    r = routing["routes"].get(f.id, routing["default"])
    return {"finding_id": f.id, "title": f.title, **r}


def process(text: str, triggers: dict, routing: dict, uncertainty: dict) -> dict:
    findings = dedupe(extract(text, triggers, uncertainty))
    triggers_found = [f for f in findings if f.status in ("trigger", "uncertain")]
    uncertain = [f for f in findings if f.status == "uncertain"]
    reviews = [
        {"finding": f.to_dict(), "suggested_route": _suggested_route(f, routing)}
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
