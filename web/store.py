"""In-memory хранилище маршрутов для прототипа рабочего места координатора.

Данные строятся из реального прогона движка (data/analysis.jsonl).
Хранилище живёт в памяти процесса — для демо этого достаточно;
эндпоинты описаны так, чтобы позже заменить источник на реальную МИС.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ANALYSIS = os.path.join(ROOT, "data", "analysis.jsonl")

STUDY_NAMES = {
    "протоколы Ж ОМТ": "УЗИ органов малого таза",
    "протоколы ЖП": "УЗИ органов брюшной полости",
    "протоколы вены нижних конечностей": "Дуплексное сканирование нижних конечностей",
    "протоколы молочная железо": "УЗИ молочных желез",
    "протоколы молочная железа": "УЗИ молочных желез",
    "протоколы предстательная железа": "ТРУЗИ предстательной железы",
    "протоколы щитовидная железа": "УЗИ щитовидной железы",
}

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

# Канонические шаги маршрута. Код -> (подпись, требуется ли для "хирургического" маршрута)
STEPS = [
    ("notification", "Уведомление пациенту отправлено (авто)"),
    ("booked", "Запись к профильному специалисту"),
    ("visit", "Приём состоялся"),
    ("decision", "Врач определил тактику"),
    ("hospital", "Направление на госпитализацию"),
    ("hospital_date", "Госпитализация назначена"),
    ("operated", "Операция выполнена"),
    ("followup", "Контрольный визит"),
]

NEXT_ACTION = {
    None: "book",
    "notification": "book",
    "booked": "visit",
    "visit": "decision",
    "decision": "hospital",
    "hospital": "hospital_date",
    "hospital_date": "operated",
    "operated": "followup",
    "followup": "close",
}

ACTION_TO_STEP = {
    "book": "booked",
    "visit": "visit",
    "decision": "decision",
    "hospital": "hospital",
    "hospital_date": "hospital_date",
    "operated": "operated",
    "followup": "followup",
    "close": "closed",
}

ACTION_LABELS = {
    "book": "Пациент записан",
    "visit": "Приём состоялся",
    "decision": "Тактика определена",
    "hospital": "Направлен на госпитализацию",
    "hospital_date": "Назначена дата госпитализации",
    "operated": "Операция выполнена",
    "followup": "Назначен контрольный визит",
    "close": "Маршрут закрыт",
    "no_show": "Неявка — запущен возврат",
    "resend": "Уведомление отправлено повторно",
    "call": "Задача на обзвон создана",
    "not_engaged": "Маршрут не реализован / пациент не вовлечён",
}

PRIORITY_ORDER = {"emergency": 0, "urgent": 1, "planned": 2, "watch": 3}

PRIORITY_META = {
    "emergency": {"label": "Экстренно", "sla_days": 1, "color": "red"},
    "urgent": {"label": "Срочно", "sla_days": 3, "color": "orange"},
    "planned": {"label": "Планово", "sla_days": 14, "color": "blue"},
    "watch": {"label": "Наблюдение", "sla_days": 30, "color": "gray"},
}

TRANSLIT = {
    "Оперирующий гинеколог": "гинеколога",
    "Гинеколог": "гинеколога",
    "Маммолог / онколог": "маммолога",
    "Хирург": "хирурга",
    "Эндокринолог / хирург": "эндокринолога",
    "Сосудистый хирург (срочно)": "сосудистого хирурга",
    "Сосудистый хирург": "сосудистого хирурга",
    "Уролог": "уролога",
    "Профильный специалист": "профильного специалиста",
}


def _clean(text: str) -> str:
    return text.replace("\u00a0", " ").replace("ё", "е")


def _parse_age(text: str) -> int | None:
    text = _clean(text)
    m = re.search(r"Возраст на момент осмотра:\s*(\d+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"Дата рождения:\s*(\d{2})\.(\d{2})\.(\d{4})", text)
    if m:
        return 2026 - int(m.group(3))
    m = re.search(r"Дата рождения:\s*(\d{1,2})\s+([а-я]+)\s+(\d{4})", text, re.I)
    if m and m.group(2).lower() in MONTHS:
        return 2026 - int(m.group(3))
    return None


def _all_dates(text: str) -> list[datetime]:
    text = _clean(text)
    out: list[datetime] = []
    for m in re.finditer(r"(\d{2})\.(\d{2})\.(\d{4})", text):
        out.append(datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), 10, 0))
    for m in re.finditer(r"(\d{1,2})\s+([а-я]+)\s+(\d{4})", text, re.I):
        mo = m.group(2).lower()
        if mo in MONTHS:
            out.append(datetime(int(m.group(3)), MONTHS[mo], int(m.group(1)), 10, 0))
    return out


def _sex(text: str, category: str) -> str:
    m = re.search(r"Пол:\s*([ЖМжм])", text)
    if m:
        return "Ж" if m.group(1).upper() == "Ж" else "М"
    if "предстательная" in category:
        return "М"
    return "Ж"


_DATE_LABELS = ["Дата выполнения", "Дата приема", "Дата исследования", "Дата осмотра"]


def _date_after(text: str, label: str) -> datetime | None:
    text = _clean(text)
    m = re.search(re.escape(label) + r"[^\d]{0,20}(\d{2})\.(\d{2})\.(\d{4})", text, re.I)
    if m:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), 10, 0)
    m = re.search(re.escape(label) + r"[^\d]{0,20}(\d{1,2})\s+([а-я]+)\s+(\d{4})", text, re.I)
    if m and m.group(2).lower() in MONTHS:
        return datetime(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)), 10, 0)
    return None


def _study_date(text: str) -> datetime:
    for label in _DATE_LABELS:
        d = _date_after(text, label)
        if d:
            return d
    dates = _all_dates(text)
    recent = [d for d in dates if d.year >= 2026]
    if recent:
        return min(recent)
    if dates:
        return max(dates)
    return datetime(2026, 9, 11, 10, 0)


def _pid(protocol_id: str) -> str:
    h = hashlib.sha1(protocol_id.encode("utf-8")).hexdigest()
    return "П-" + str(int(h[:6], 16) % 9000 + 1000)


def _notification_text(routes_list: list[dict]) -> str:
    """Нейтральный текст: НИКАКОГО диагноза. Если маршрутов несколько —
    одно агрегированное уведомление (иначе пациент получит спам из пушей)."""
    specs: list[str] = []
    for r in routes_list:
        s = TRANSLIT.get(r.get("specialist", ""), "")
        if s and s not in specs:
            specs.append(s)
    if not specs:
        who = "врача профильного специалиста"
    elif len(specs) == 1:
        who = f"врача-{specs[0]}"
    else:
        who = "специалистов: " + ", ".join(specs)
    return (
        "Ваш результат исследования готов. В заключении описаны изменения, "
        f"по которым рекомендуется консультация {who} для определения дальнейшей тактики.\n\n"
        "Вы можете записаться на очную консультацию или получить онлайн-консультацию."
    )


def _load_engine() -> list[dict]:
    with open(ANALYSIS, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]

    routes: list[dict] = []
    n = 0
    for rec in records:
        an = rec["analysis"]
        if not an["is_trigger"]:
            continue
        n += 1
        date = _study_date(rec["text"])
        route = {
            "id": f"R-{n:03d}",
            "patient": {
                "id": _pid(rec["id"]),
                "age": _parse_age(rec["text"]),
                "sex": _sex(rec["text"], rec["category"]),
            },
            "source": {
                "study": STUDY_NAMES.get(rec["category"], rec["category"]),
                "protocol_id": rec["id"],
                "file": rec["file"],
                "date": date.isoformat(),
            },
            "protocol_text": rec["text"],
            "triggers": an["triggers"],
            "route": an["routes"][0] if an["routes"] else {},
            "all_routes": an["routes"],
            "status": "notification",
            "urgent": bool(an["routes"] and an["routes"][0].get("urgent")),
            "created_at": (date + timedelta(minutes=2)).isoformat(),
            "due_at": (date + timedelta(days=an["routes"][0].get("target_days", 14))).isoformat()
            if an["routes"] else None,
            "step": "notification",
            "history": [],
            "notifications": [],
            "tasks": [],
        }
        route["notification_text"] = _notification_text(an["routes"])
        route["history"].append(
            {
                "at": route["created_at"],
                "event": "trigger_detected",
                "label": f"Выявлена находка: {an['triggers'][0]['title']}"
                if an["triggers"] else "Триггер",
            }
        )
        routes.append(route)

    # стартовое системное время — конец последнего исследования
    if routes:
        start = max(datetime.fromisoformat(r["created_at"]) for r in routes)
    else:
        start = datetime(2026, 9, 11, 10, 0)
    return routes, start


LABELED = os.path.join(ROOT, "data", "labeled_routes.jsonl")


def _protocol_texts() -> dict:
    """Карта protocol_id -> полный текст протокола (для раскрытия в интерфейсе врача)."""
    texts: dict[str, str] = {}
    if os.path.exists(ANALYSIS):
        with open(ANALYSIS, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                texts[rec["id"]] = rec["text"]
    return texts


def _load_labeled(path: str) -> list[dict]:
    """Загружает результат команды ML/разметки (см. docs/api_contract.md).

    Маршрут создаётся только по находкам со status == "trigger".
    """
    with open(path, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]

    texts = _protocol_texts()
    routes: list[dict] = []
    n = 0
    for rec in records:
        findings = rec.get("findings", [])
        trig = [f for f in findings if f.get("status") in ("trigger", "uncertain")]
        if not trig:
            continue
        n += 1
        study = rec.get("study", {})
        date = (
            datetime.fromisoformat(study["date"])
            if study.get("date")
            else datetime(2026, 9, 11, 10, 0)
        )
        r = rec.get("route") or {}
        routes_list = rec.get("routes")
        if routes_list is None:
            routes_list = [r] if r else []
        primary = routes_list[0] if routes_list else {}
        protocol_id = rec.get("protocol_id", "")
        route = {
            "id": f"R-{n:03d}",
            "patient": rec.get("patient")
            or {"id": _pid(protocol_id), "age": None, "sex": "Ж"},
            "source": {
                "study": study.get("type", ""),
                "protocol_id": protocol_id,
                "file": protocol_id.split("/")[-1],
                "date": date.isoformat(),
            },
            "protocol_text": rec.get("protocol_text") or texts.get(protocol_id, ""),
            "triggers": trig,
            "route": primary,
            "all_routes": routes_list,
            "status": "notification",
            "urgent": bool(primary.get("urgent")),
            "created_at": (date + timedelta(minutes=2)).isoformat(),
            "due_at": (date + timedelta(days=primary.get("target_days", 14))).isoformat(),
            "step": "notification",
            "history": [],
            "notifications": [],
            "tasks": [],
        }
        route["notification_text"] = _notification_text(routes_list)
        route["history"].append(
            {
                "at": route["created_at"],
                "event": "trigger_detected",
                "label": f"Выявлена находка: {trig[0]['title']}",
            }
        )
        routes.append(route)

    if routes:
        start = max(datetime.fromisoformat(r["created_at"]) for r in routes)
    else:
        start = datetime(2026, 9, 11, 10, 0)
    return routes, start


def _load() -> list[dict]:
    """Если команда ML положила data/labeled_routes.jsonl — используем его,
    иначе работаем на встроенном движке."""
    if os.path.exists(LABELED):
        return _load_labeled(LABELED)
    return _load_engine()


def _routing_rules() -> dict:
    with open(os.path.join(ROOT, "rules", "routing.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _ruleset_info() -> dict:
    """Версия и контрольная сумма зафиксированных правил (см. scripts/integrity.py)."""
    try:
        with open(os.path.join(ROOT, "rules", "ruleset.json"), encoding="utf-8") as fh:
            rs = json.load(fh)
        return {
            "version": rs.get("version"),
            "checksum": rs.get("checksum"),
            "findings": rs.get("findings"),
            "frozen_at": rs.get("frozen_at"),
        }
    except Exception:
        return {}


def _reviews_from_engine() -> list[dict]:
    with open(ANALYSIS, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]
    reviews: list[dict] = []
    n = 0
    for rec in records:
        an = rec["analysis"]
        for item in an.get("reviews", []):
            n += 1
            date = _study_date(rec["text"])
            reviews.append(
                {
                    "id": f"REV-{n:03d}",
                    "patient": {
                        "id": _pid(rec["id"]),
                        "age": _parse_age(rec["text"]),
                        "sex": _sex(rec["text"], rec["category"]),
                    },
                    "source": {
                        "study": STUDY_NAMES.get(rec["category"], rec["category"]),
                        "protocol_id": rec["id"],
                        "date": date.isoformat(),
                    },
                    "protocol_text": rec["text"],
                    "finding": item["finding"],
                    "suggested_route": item.get("suggested_route", {}),
                    "status": "pending",
                    "history": [
                        {"at": date.isoformat(), "label": f"Требует уточнения: {item['finding']['title']}"}
                    ],
                }
            )
    return reviews


def _reviews_from_labeled(path: str) -> list[dict]:
    routing = _routing_rules()
    with open(path, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    texts = _protocol_texts()
    reviews: list[dict] = []
    n = 0
    for rec in records:
        study = rec.get("study", {})
        date = datetime.fromisoformat(study["date"]) if study.get("date") else datetime(2026, 9, 11, 10, 0)
        protocol_id = rec.get("protocol_id", "")
        for f in rec.get("findings", []):
            if f.get("status") != "uncertain":
                continue
            n += 1
            r = routing["routes"].get(f["id"], routing["default"])
            reviews.append(
                {
                    "id": f"REV-{n:03d}",
                    "patient": rec.get("patient") or {"id": _pid(protocol_id), "age": None, "sex": "Ж"},
                    "source": {"study": study.get("type", ""), "protocol_id": protocol_id, "date": date.isoformat()},
                    "protocol_text": texts.get(protocol_id, ""),
                    "finding": f,
                    "suggested_route": {"finding_id": f["id"], "title": f["title"], **r},
                    "status": "pending",
                    "history": [
                        {"at": date.isoformat(), "label": f"Требует уточнения: {f['title']}"}
                    ],
                }
            )
    return reviews


def _load_reviews() -> list[dict]:
    if os.path.exists(LABELED):
        return _reviews_from_labeled(LABELED)
    return _reviews_from_engine()


def _conclusion(text: str, limit: int = 300) -> str:
    """Содержательное заключение (пропускает дисклеймеры «не является диагнозом»)."""
    best = ""
    for m in re.finditer(r"заключени[ея]", text, re.I):
        frag = " ".join(text[m.start(): m.start() + limit].split())
        if "не является" in frag[:80].lower():
            continue
        best = frag
    return best or " ".join(text[-limit:].split())


def _load_normals() -> list[dict]:
    """Протоколы без значимых находок — сохраняем отдельно, чтобы ничего не терялось."""
    out: list[dict] = []
    if not os.path.exists(ANALYSIS):
        return out
    n = 0
    with open(ANALYSIS, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            an = rec["analysis"]
            if an["is_trigger"] or an.get("uncertain"):
                continue
            n += 1
            date = _study_date(rec["text"])
            out.append(
                {
                    "id": f"N-{n:03d}",
                    "patient": {
                        "id": _pid(rec["id"]),
                        "age": _parse_age(rec["text"]),
                        "sex": _sex(rec["text"], rec["category"]),
                    },
                    "source": {
                        "study": STUDY_NAMES.get(rec["category"], rec["category"]),
                        "protocol_id": rec["id"],
                        "file": rec["file"],
                        "date": date.isoformat(),
                    },
                    "findings": an["findings"],
                    "conclusion": _conclusion(rec["text"]),
                    "protocol_text": rec["text"],
                    "status": "no_pathology",
                    "at": date.isoformat(),
                }
            )
    return out


def _real_now() -> datetime:
    """Местное текущее время. Пытаемся синхронизироваться с интернетом и
    приводим к часовому поясу компьютера; иначе берём системное время."""
    try:
        import urllib.request

        req = urllib.request.Request(
            "https://worldtimeapi.org/api/ip", headers={"User-Agent": "sm-clinic"}
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.load(r)
        dt = datetime.fromisoformat(data["datetime"])
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)  # в местный часовой пояс
        return dt
    except Exception:
        return datetime.now()


def _count_protocols() -> int:
    """Общее число протоколов — знаменатель для статистики (все исследования)."""
    if os.path.exists(ANALYSIS):
        with open(ANALYSIS, encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
    return 0


def _shift_routes(routes: list[dict], reviews: list[dict], normals: list[dict], delta) -> None:
    """Сдвигает все даты данных на delta, чтобы демо было актуальным «сегодня»."""

    def s(value: str) -> str:
        try:
            return (datetime.fromisoformat(value) + delta).isoformat()
        except Exception:
            return value

    for r in routes:
        for k in ("created_at", "due_at"):
            if r.get(k):
                r[k] = s(r[k])
        for coll in ("notifications", "history", "tasks"):
            for item in r.get(coll, []):
                if item.get("at"):
                    item["at"] = s(item["at"])
    for rv in reviews:
        src = rv.get("source", {})
        if src.get("date"):
            src["date"] = s(src["date"])
        for item in rv.get("history", []):
            if item.get("at"):
                item["at"] = s(item["at"])
        if rv.get("protocol_text"):
            pass
    for n in normals:
        src = n.get("source", {})
        if src.get("date"):
            src["date"] = s(src["date"])


class Store:
    def __init__(self) -> None:
        self.routes, _start = _load()
        self.reviews = _load_reviews()
        self.normals = _load_normals()
        self._next_n = len(self.routes)
        self.protocols_total = _count_protocols()

        # Привязка к реальному времени: сдвигаем даты данных так,
        # чтобы последнее исследование соответствовало «сейчас».
        self.now = _real_now()
        latest = None
        for r in self.routes:
            try:
                d = datetime.fromisoformat(r["created_at"])
                if latest is None or d > latest:
                    latest = d
            except Exception:
                pass
        if latest:
            _shift_routes(self.routes, self.reviews, self.normals, self.now - latest)

        # при старте считаем уведомления отправленными
        for r in self.routes:
            self._send_notification(r, "Первичное уведомление (авто)")

    # ---------- чтение ----------
    def list_routes(self, status: str | None = None, urgent: bool | None = None,
                    specialty: str | None = None, priority: str | None = None,
                    q: str | None = None) -> list[dict]:
        out = []
        for r in self.routes:
            if status and r["status"] != status:
                continue
            if urgent is not None and r["urgent"] != urgent:
                continue
            if priority and r["route"].get("priority", "planned") != priority:
                continue
            if specialty and r["route"].get("specialist") != specialty:
                continue
            if q:
                hay = f"{r['id']} {r['patient']['id']} {r['source']['study']} " \
                      f"{' '.join(t['title'] for t in r['triggers'])}".lower()
                if q.lower() not in hay:
                    continue
            out.append(self._short(r))
        out.sort(key=lambda x: (PRIORITY_ORDER.get(x["priority"], 9), x["due_at"] or ""))
        return out

    def get(self, rid: str) -> dict | None:
        for r in self.routes:
            if r["id"] == rid:
                return self._full(r)
        return None

    def _short(self, r: dict) -> dict:
        return {
            "id": r["id"],
            "patient": r["patient"],
            "study": r["source"]["study"],
            "date": r["source"]["date"],
            "trigger": r["triggers"][0]["title"] if r["triggers"] else "",
            "routes_count": len(r["all_routes"]),
            "specialist": r["route"].get("specialist", ""),
            "next_step": r["route"].get("next_step", ""),
            "status": r["status"],
            "step": r["step"],
            "urgent": r["urgent"],
            "priority": r["route"].get("priority", "planned"),
            "priority_reason": r["route"].get("priority_reason", ""),
            "due_at": r["due_at"],
        }

    def _full(self, r: dict) -> dict:
        return {
            **self._short(r),
            "protocol_id": r["source"]["protocol_id"],
            "file": r["source"]["file"],
            "triggers": r["triggers"],
            "all_routes": r["all_routes"],
            "planned_step": r["route"].get("planned_step", ""),
            "department": r["route"].get("department", ""),
            "target_days": r["route"].get("target_days"),
            "created_at": r["created_at"],
            "notification_text": r["notification_text"],
            "protocol_text": r.get("protocol_text", ""),
            "notifications": r["notifications"],
            "history": r["history"],
            "tasks": r["tasks"],
            "steps": self._steps(r),
            "next_action": NEXT_ACTION.get(r["step"]) or NEXT_ACTION.get(None),
        }

    def _steps(self, r: dict) -> list[dict]:
        order = [s[0] for s in STEPS]
        cur = r["step"]
        # "closed" -> всё выполнено
        cur_idx = len(order) if cur == "closed" else (order.index(cur) if cur in order else 0)
        out = []
        for i, (code, label) in enumerate(STEPS):
            state = "done" if i < cur_idx else ("current" if i == cur_idx else "pending")
            out.append({"code": code, "label": label, "state": state})
        return out

    # ---------- действия ----------
    def _send_notification(self, r: dict, label: str) -> None:
        r["notifications"].append(
            {
                "at": (self.now if r["notifications"] else r["created_at"]),
                "channel": "push + личный кабинет",
                "label": label,
                "text": r["notification_text"],
            }
        )

    def act(self, rid: str, action: str) -> dict | None:
        r = next((x for x in self.routes if x["id"] == rid), None)
        if r is None:
            return None
        now = self.now.isoformat()
        if action == "no_show":
            r["status"] = "no_show"
            r["step"] = "notification"
            r["history"].append({"at": now, "event": "no_show", "label": ACTION_LABELS["no_show"]})
            self._send_notification(r, "Просьба перезаписаться (после неявки)")
        elif action == "resend":
            self._send_notification(r, "Повторное уведомление")
            r["history"].append({"at": now, "event": "resend", "label": ACTION_LABELS["resend"]})
        elif action == "call":
            r["tasks"].append({"at": now, "label": "Обзвонить пациента", "owner": "Координатор"})
            r["history"].append({"at": now, "event": "call", "label": ACTION_LABELS["call"]})
        elif action == "not_engaged":
            r["status"] = "not_engaged"
            r["history"].append({"at": now, "event": "not_engaged", "label": ACTION_LABELS["not_engaged"]})
        elif action in ACTION_TO_STEP:
            step = ACTION_TO_STEP[action]
            r["step"] = step
            r["status"] = "closed" if step == "closed" else step
            r["history"].append({"at": now, "event": action, "label": ACTION_LABELS[action]})
        return self._full(r)

    # ---------- модельное время ----------
    def advance(self, hours: float) -> dict:
        self.now += timedelta(hours=hours)
        events = []
        for r in self.routes:
            if r["step"] == "closed" or r["status"] in ("not_engaged",):
                continue
            created = datetime.fromisoformat(r["created_at"])
            elapsed_h = (self.now - created).total_seconds() / 3600
            sent = [n["label"] for n in r["notifications"]]
            if r["step"] == "notification":
                if elapsed_h >= 24 and "Напоминание через 24 часа" not in sent:
                    self._send_notification(r, "Напоминание через 24 часа")
                    events.append((r["id"], "напоминание 24ч"))
                if elapsed_h >= 72 and "Напоминание через 72 часа" not in sent:
                    self._send_notification(r, "Напоминание через 72 часа")
                    events.append((r["id"], "напоминание 72ч"))
                if elapsed_h >= 120 and not any(t["label"] == "Обзвонить пациента" for t in r["tasks"]):
                    r["tasks"].append({"at": self.now.isoformat(), "label": "Обзвонить пациента", "owner": "Координатор"})
                    events.append((r["id"], "задача на обзвон 5 дней"))
                if elapsed_h >= 720:
                    r["status"] = "not_engaged"
                    r["history"].append({"at": self.now.isoformat(), "event": "not_engaged",
                                         "label": ACTION_LABELS["not_engaged"]})
                    events.append((r["id"], "маршрут не реализован 30 дней"))
        return {"now": self.now.isoformat(), "events": events}

    # ---------- очередь «Требует уточнения» ----------
    def _review(self, rv: dict) -> dict:
        return dict(rv)

    def list_reviews(self, status: str | None = "pending") -> list[dict]:
        return [self._review(r) for r in self.reviews if not status or r["status"] == status]

    def list_normals(self) -> list[dict]:
        return [dict(n) for n in self.normals]

    def resolve_review(self, rid: str, decision: str) -> dict | None:
        rv = next((x for x in self.reviews if x["id"] == rid), None)
        if rv is None:
            return None
        now = self.now.isoformat()
        if decision == "confirm":
            existing = next(
                (r for r in self.routes if r["source"]["protocol_id"] == rv["source"]["protocol_id"]),
                None,
            )
            if existing is not None:
                rv["status"] = "accepted"
                rv["history"].append({"at": now, "label": "Пометка снята — маршрут уже создан, пуш отправлен"})
                return {"review": self._review(rv), "route": self._full(existing)}
            self._next_n += 1
            date = datetime.fromisoformat(rv["source"]["date"])
            route = {
                "id": f"R-{self._next_n:03d}",
                "patient": rv["patient"],
                "source": {
                    "study": rv["source"]["study"],
                    "protocol_id": rv["source"]["protocol_id"],
                    "file": rv["source"]["protocol_id"].split("/")[-1],
                    "date": rv["source"]["date"],
                },
                "triggers": [rv["finding"]],
                "route": rv["suggested_route"],
                "all_routes": [rv["suggested_route"]],
                "status": "notification",
                "urgent": bool(rv["suggested_route"].get("urgent")),
                "created_at": (date + timedelta(minutes=2)).isoformat(),
                "due_at": (date + timedelta(days=rv["suggested_route"].get("target_days", 14))).isoformat(),
                "step": "notification",
                "history": [],
                "notifications": [],
                "tasks": [],
            }
            route["notification_text"] = _notification_text([rv["suggested_route"]])
            route["history"].append(
                {
                    "at": now,
                    "event": "confirmed_trigger",
                    "label": f"Подтверждено координатором: {rv['finding']['title']}",
                }
            )
            self.routes.append(route)
            self._send_notification(route, "Первичное уведомление (авто)")
            rv["status"] = "confirmed"
            rv["history"].append({"at": now, "label": "Подтверждено — создан маршрут"})
            return {"review": self._review(rv), "route": self._full(route)}

        rv["status"] = "rejected"
        rv["history"].append({"at": now, "label": "Отклонено координатором"})
        return {"review": self._review(rv), "route": None}

    # ---------- приём нового протокола («живой» поток docx -> находки -> маршрут) ----------
    def ingest(self, text: str, protocol_id: str = "Загруженный протокол",
               study_type: str = "", patient: dict | None = None) -> dict:
        from app.processor import load_rules, process as run_process

        triggers_rules, routing, uncertainty = load_rules()
        res = run_process(text, triggers_rules, routing, uncertainty)
        date = _study_date(text)
        if patient is None:
            patient = {
                "id": _pid(protocol_id + text[:32]),
                "age": _parse_age(text),
                "sex": _sex(text, study_type or ""),
            }
        source = {
            "study": study_type or "Загруженный протокол",
            "protocol_id": protocol_id,
            "file": protocol_id,
            "date": date.isoformat(),
        }

        created_routes = []
        if res["routes"]:
            self._next_n += 1
            routes_list = res["routes"]
            primary = routes_list[0]
            route = {
                "id": f"R-{self._next_n:03d}",
                "patient": patient,
                "source": source,
                "protocol_text": text,
                "triggers": res["triggers"],
                "route": primary,
                "all_routes": routes_list,
                "status": "notification",
                "urgent": bool(primary.get("urgent")),
                "created_at": (date + timedelta(minutes=2)).isoformat(),
                "due_at": (date + timedelta(days=primary.get("target_days", 14))).isoformat(),
                "step": "notification",
                "history": [
                    {
                        "at": date.isoformat(),
                        "event": "trigger_detected",
                        "label": f"Выявлена находка: {res['triggers'][0]['title']}",
                    }
                ],
                "notifications": [],
                "tasks": [],
            }
            route["notification_text"] = _notification_text(routes_list)
            self.routes.append(route)
            self._send_notification(route, "Первичное уведомление (авто)")
            created_routes.append(self._full(route))

        created_reviews = []
        for item in res["reviews"]:
            rv = {
                "id": f"REV-{len(self.reviews) + 1:03d}",
                "patient": patient,
                "source": source,
                "protocol_text": text,
                "finding": item["finding"],
                "suggested_route": item.get("suggested_route", {}),
                "status": "pending",
                "history": [
                    {"at": date.isoformat(), "label": f"Требует уточнения: {item['finding']['title']}"}
                ],
            }
            self.reviews.append(rv)
            created_reviews.append(self._review(rv))

        created_normal = None
        if not res["routes"] and not res["reviews"]:
            created_normal = {
                "id": f"N-{len(self.normals) + 1:03d}",
                "patient": patient,
                "source": source,
                "findings": res["findings"],
                "conclusion": _conclusion(text),
                "protocol_text": text,
                "status": "no_pathology",
                "at": date.isoformat(),
            }
            self.normals.insert(0, created_normal)
            saved_to = "norm"
        elif res["routes"]:
            saved_to = "route"
        else:
            saved_to = "review"

        return {
            **source,
            "patient": patient,
            "study": {"type": source["study"], "date": source["date"]},
            "findings": res["findings"],
            "routes": res["routes"],
            "is_trigger": res["is_trigger"],
            "created_routes": created_routes,
            "created_reviews": created_reviews,
            "created_normal": created_normal,
            "saved_to": saved_to,
        }

    # ---------- дашборд ----------
    def dashboard(self) -> dict:
        total = len(self.routes)
        by_status: dict[str, int] = {}
        by_specialty: dict[str, int] = {}
        for r in self.routes:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            spec = r["route"].get("specialist", "")
            by_specialty[spec] = by_specialty.get(spec, 0) + 1

        def cnt(*steps: str) -> int:
            return sum(1 for r in self.routes if r["step"] in steps or r["status"] in steps)

        funnel = [
            {"label": "Выявлена значимая находка", "value": total},
            {"label": "Уведомление отправлено", "value": total},
            {"label": "Записались к специалисту", "value": cnt("booked", "visit", "decision", "hospital", "hospital_date", "operated", "followup", "closed")},
            {"label": "Приём состоялся", "value": cnt("visit", "decision", "hospital", "hospital_date", "operated", "followup", "closed")},
            {"label": "Направлены на госпитализацию", "value": cnt("hospital", "hospital_date", "operated", "followup", "closed")},
            {"label": "Оперированы", "value": cnt("operated", "followup", "closed")},
            {"label": "Контрольный визит назначен", "value": cnt("followup", "closed")},
        ]
        return {
            "now": self.now.isoformat(),
            "total": total,
            "protocols_total": self.protocols_total,
            "urgent": sum(1 for r in self.routes if r["urgent"]),
            "by_status": by_status,
            "by_specialty": by_specialty,
            "funnel": funnel,
        }

    def meta(self) -> dict:
        return {
            "specialties": sorted({r["route"].get("specialist", "") for r in self.routes if r["route"].get("specialist")}),
            "statuses": ["notification", "booked", "visit", "decision", "hospital",
                         "hospital_date", "operated", "followup", "closed", "no_show", "not_engaged"],
            "priorities": PRIORITY_META,
            "action_labels": ACTION_LABELS,
            "pending_reviews": len(self.list_reviews()),
            "ruleset": _ruleset_info(),
        }


STORE = Store()
