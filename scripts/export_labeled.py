"""Экспортирует результат движка в формат контракта (docs/api_contract.md).

Зачем: показать команде ML/разметки эталонный формат, который ждёт интерфейс.
Полученный файл можно взять за образец разметки.

Использование:
    python scripts/export_labeled.py
Результат: data/labeled_routes.sample.jsonl
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from web.store import (  # noqa: E402
    ANALYSIS, STUDY_NAMES, _parse_age, _pid, _sex, _study_date,
)

OUT = os.path.join(HERE, "data", "labeled_routes.sample.jsonl")
ACTIVE = os.path.join(HERE, "data", "labeled_routes.jsonl")


def main() -> None:
    with open(ANALYSIS, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]

    rows: list[str] = []
    for rec in records:
        an = rec["analysis"]
        text, cat = rec["text"], rec["category"]
        record = {
            "protocol_id": rec["id"],
            "patient": {
                "id": _pid(rec["id"]),
                "age": _parse_age(text),
                "sex": _sex(text, cat),
            },
            "study": {
                "type": STUDY_NAMES.get(cat, cat),
                "date": _study_date(text).isoformat(),
            },
            "findings": an["findings"],
            "routes": an["routes"],
        }
        rows.append(json.dumps(record, ensure_ascii=False))

    # образец для команды ML + рабочий файл, который подхватывает интерфейс
    for path in (OUT, ACTIVE):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(rows) + "\n")
        print(f"Записано {len(rows)} записей -> {path}")


if __name__ == "__main__":
    main()
