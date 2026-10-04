"""Проверка файла разметки на соответствие контракту (docs/api_contract.md).

Запускается без сторонних библиотек:
    python scripts/validate_labels.py data/labeled_routes.jsonl

Код возврата 0 — файл валиден, 1 — есть ошибки.
Команда ML может гонять этот скрипт у себя как приёмку формата.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

STATUSES = {"trigger", "uncertain", "negated"}
SEVERITIES = {"urgent", "planned", "watch"}
PRIORITIES = {"emergency", "urgent", "planned", "watch"}

REQUIRED_TOP = ["protocol_id", "study", "findings"]
REQUIRED_FINDING = ["id", "title", "status", "evidence"]
REQUIRED_ROUTE = ["specialist", "next_step"]


def check_record(rec: dict, line: int, errors: list, warnings: list, notices: list) -> None:
    where = f"строка {line}"
    for key in REQUIRED_TOP:
        if key not in rec:
            errors.append(f"{where}: нет обязательного поля '{key}'")
    if errors and not all(k in rec for k in REQUIRED_TOP):
        return

    study = rec.get("study", {})
    if not study.get("type"):
        errors.append(f"{where}: study.type пустой")
    date = study.get("date", "")
    if date:
        try:
            datetime.fromisoformat(date)
        except ValueError:
            errors.append(f"{where}: study.date не в формате ISO 8601 ({date!r}), пример 2026-08-13T10:00:00")
    else:
        errors.append(f"{where}: study.date пустой")

    patient = rec.get("patient") or {}
    if patient and not patient.get("id"):
        errors.append(f"{where}: patient.id пустой")
    if patient.get("sex") and patient["sex"] not in ("Ж", "М"):
        errors.append(f"{where}: patient.sex должен быть 'Ж' или 'М'")

    findings = rec.get("findings")
    if not isinstance(findings, list):
        errors.append(f"{where}: findings должен быть списком")
        return
    triggers = 0
    for i, f in enumerate(findings):
        fw = f"{where}, находка #{i} ({f.get('id', '?')})"
        for key in REQUIRED_FINDING:
            if not f.get(key):
                errors.append(f"{fw}: нет обязательного поля '{key}'")
        if f.get("status") not in STATUSES:
            errors.append(f"{fw}: status должен быть одним из {sorted(STATUSES)}")
        if f.get("status") == "trigger":
            triggers += 1
        if f.get("severity") and f["severity"] not in SEVERITIES:
            errors.append(f"{fw}: severity должен быть одним из {sorted(SEVERITIES)}")
        c = f.get("confidence")
        if c is not None and not (isinstance(c, (int, float)) and 0 <= c <= 1):
            errors.append(f"{fw}: confidence должен быть числом от 0 до 1")
        if f.get("status") == "trigger" and not f.get("attributes"):
            notices.append(f"{fw}: нет attributes (размер/BI-RADS и т.п.) — не обязательно")

    routes = rec.get("routes")
    if routes is None and "route" in rec:
        routes = [rec["route"]] if rec["route"] else []
        notices.append(f"{where}: устаревший формат route — используйте routes: []")
    if not isinstance(routes, list):
        errors.append(f"{where}: routes должен быть списком")
        routes = []

    if triggers > 0 and not routes:
        errors.append(f"{where}: есть триггеры, но routes пуст — маршрут потеряется")
    if triggers == 0 and routes:
        warnings.append(f"{where}: нет находок со status=trigger, но routes непустой")
    if triggers == 0:
        notices.append(f"{where}: нет находок со status=trigger — норма, маршрут не создаётся")

    for j, r in enumerate(routes):
        rw = f"{where}, маршрут #{j}"
        for key in REQUIRED_ROUTE:
            if not r.get(key):
                errors.append(f"{rw}: {key} пустой")
        if r.get("priority") and r["priority"] not in PRIORITIES:
            errors.append(f"{rw}: priority должен быть одним из {sorted(PRIORITIES)}")
        if not r.get("priority"):
            warnings.append(f"{rw}: priority не задан — интерфейс возьмёт значение по умолчанию")
        if not r.get("priority_reason"):
            warnings.append(f"{rw}: нет priority_reason (обоснование срочности)")
        td = r.get("target_days")
        if td is not None and not isinstance(td, int):
            errors.append(f"{rw}: target_days должен быть целым числом")


def main() -> int:
    if len(sys.argv) < 2:
        print("Использование: python scripts/validate_labels.py <файл.jsonl>")
        return 1
    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"Файл не найден: {path}")
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    notices: list[str] = []
    total = 0
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"строка {i}: битый JSON ({e})")
                continue
            check_record(rec, i, errors, warnings, notices)

    print(f"Записей: {total} | ошибок: {len(errors)} | предупреждений: {len(warnings)} | инфо: {len(notices)}")
    if errors:
        print("\nОШИБКИ (файл не соответствует контракту):")
        for e in errors:
            print("  ✗", e)
    if warnings:
        print("\nПРЕДУПРЕЖДЕНИЯ (не блокируют, но исправьте):")
        for w in warnings:
            print("  !", w)
    if not errors:
        print("\n✓ Файл соответствует контракту.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
