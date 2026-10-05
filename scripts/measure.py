"""Оценка ядра на выданных протоколах: сколько отклонений находим и что с нормой.

Эталон по умолчанию — 76 протоколов с отклонениями / 13 без (по разбору кейса).
Список «нормы» можно переопределить: положите ids в data/normals.txt (по одному на строку).

Запуск:
    python scripts/measure.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS = os.path.join(HERE, "data", "analysis.jsonl")
NORMALS_FILE = os.path.join(HERE, "data", "normals.txt")

# Эталон по умолчанию: 13 протоколов без клинически значимых триггеров.
DEFAULT_NORMALS = {
    "протоколы вены нижних конечностей/нижние конечности (2).docx",
    "протоколы вены нижних конечностей/нижние конечности (10).docx",
    "протоколы Ж ОМТ/1 Ж ОМТ (4).docx",
    "протоколы ЖП/1 ЖП (15).docx",
    "протоколы ЖП/1 ЖП (17).docx",
    "протоколы ЖП/1 ЖП (19).docx",
    "протоколы молочная железа/молочн железа (4).docx",
    "протоколы молочная железа/молочн железа (5).docx",
    "протоколы молочная железа/молочн железа (7).docx",
    "протоколы молочная железа/молочн железа (8).docx",
    "протоколы молочная железа/молочн железа (9).docx",
    "протоколы молочная железа/молочн железа (10).docx",
    "протоколы щитовидная железа/щитовидка (10).docx",
}


def load_normals() -> set[str]:
    if os.path.exists(NORMALS_FILE):
        with open(NORMALS_FILE, encoding="utf-8") as fh:
            return {line.strip() for line in fh if line.strip()}
    return set(DEFAULT_NORMALS)


def main() -> None:
    with open(ANALYSIS, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]

    normals = load_normals()
    tp = fp = fn = tn = 0
    missed: list[str] = []
    false_pos: list[str] = []

    for rec in records:
        is_dev = rec["id"] not in normals
        trig = rec["analysis"]["is_trigger"]
        if is_dev and trig:
            tp += 1
        elif is_dev and not trig:
            fn += 1
            missed.append(rec["id"])
        elif not is_dev and trig:
            fp += 1
            found = "; ".join(f"{f['title']}" for f in rec["analysis"]["triggers"][:3])
            false_pos.append(f"{rec['id']}  <-  {found}")
        else:
            tn += 1

    total = len(records)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    print(f"Протоколов: {total}  |  эталон: отклонений {tp + fn}, норма {fp + tn}")
    print(f"Сработал триггер: {tp + fp}")
    print(f"  Recall (полнота)  : {recall:.1%}   TP={tp}  FN={fn}")
    print(f"  Precision (точность): {precision:.1%}   FP={fp}  TN={tn}")
    print(f"  F1                : {f1:.1%}")

    if missed:
        print("\nПРОПУЩЕНЫ (есть отклонение, маршрут не создан):")
        for pid in missed:
            print(f"  - {pid}")
    if false_pos:
        print("\nЛОЖНЫЕ СРАБАТЫВАНИЯ (норма, но маршрут создан):")
        for line in false_pos:
            print(f"  - {line}")


if __name__ == "__main__":
    main()
