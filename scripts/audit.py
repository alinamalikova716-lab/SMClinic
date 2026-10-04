"""Аудит качества: сравнение решения системы с эталоном (ручной разметкой).

Режимы:
  1) python scripts/audit.py
     Строит data/audit.csv — по всем протоколам: что нашла система + заключение врача.
     Врач/эксперт читает и заполняет колонки reference_trigger (1/0) и reference_note.

  2) python scripts/audit.py --metrics
     Считает по заполненному audit.csv: precision, recall, F1, ошибки I и II рода.

Колонка reference_trigger:
  1 = в протоколе действительно есть клинически значимая находка (маршрут нужен)
  0 = значимой находки нет (маршрут не нужен)
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS = os.path.join(HERE, "data", "analysis.jsonl")
AUDIT = os.path.join(HERE, "data", "audit.csv")

ZAKL = re.compile(r"заключени[ея]", re.I)


def conclusion(text: str, limit: int = 400) -> str:
    """Вытаскивает содержательное заключение врача.

    Пропускает дисклеймеры вида «заключение не является диагнозом» —
    они не несут клинической информации.
    """
    best = ""
    for m in ZAKL.finditer(text):
        frag = text[m.start(): m.start() + limit]
        head = " ".join(frag[:80].split()).lower()
        if "не является" in head or "не является диагнозом" in head:
            continue
        best = " ".join(frag.split())
    if best:
        return best
    # если содержательного заключения нет — показать последний абзац
    return " ".join(text[-limit:].split())


def build() -> None:
    with open(ANALYSIS, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]

    with_trig = sum(1 for r in records if r["analysis"]["is_trigger"])
    print(f"Протоколов: {len(records)} | система нашла триггер: {with_trig} | "
          f"без триггера: {len(records) - with_trig}")
    print("Без триггера — эти записи надо проверить глазами (нет ли пропуска):")

    n_no = 0
    with open(AUDIT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["protocol_id", "category", "system_trigger", "system_findings",
                    "evidence", "conclusion", "reference_trigger", "reference_note"])
        for rec in records:
            an = rec["analysis"]
            titles = "; ".join(f"{f['title']} [{f['status']}]" for f in an["findings"])
            ev = " | ".join(f["evidence"] for f in an["findings"])[:400]
            concl = conclusion(rec["text"])
            w.writerow([rec["id"], rec["category"], 1 if an["is_trigger"] else 0,
                        titles, ev, concl, "", ""])
            if not an["is_trigger"] and n_no < 12:
                n_no += 1
                print(f"  - {rec['id']}")
                print(f"      {concl[:150]}")

    print()
    print(f"Таблица для проверки: {AUDIT}")
    print("Заполните reference_trigger (1/0) и reference_note, затем:")
    print("  python scripts/audit.py --metrics")


def metrics() -> None:
    if not os.path.exists(AUDIT):
        print("Сначала постройте таблицу: python scripts/audit.py")
        return
    tp = fp = fn = tn = 0
    unlabeled = 0
    fn_examples, fp_examples = [], []
    with open(AUDIT, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            ref = (row.get("reference_trigger") or "").strip()
            if ref not in ("0", "1"):
                unlabeled += 1
                continue
            sysv = 1 if row["system_trigger"] == "1" else 0
            refv = int(ref)
            if sysv == 1 and refv == 1:
                tp += 1
            elif sysv == 1 and refv == 0:
                fp += 1
                fp_examples.append(row["protocol_id"])
            elif sysv == 0 and refv == 1:
                fn += 1
                fn_examples.append(row["protocol_id"])
            else:
                tn += 1

    total = tp + fp + fn + tn
    if total == 0:
        print("Нет заполненных записей (reference_trigger). Заполните таблицу.")
        return
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / total

    print(f"Размечено записей: {total} (не размечено: {unlabeled})")
    print(f"  TP={tp}  FP={fp}  FN={fn}  TN={tn}")
    print(f"  Precision (точность)          : {precision:.2%}")
    print(f"  Recall (полнота)              : {recall:.2%}")
    print(f"  F1                            : {f1:.2%}")
    print(f"  Accuracy                      : {accuracy:.2%}")
    if fp_examples:
        print("  Ложные срабатывания (I род):", ", ".join(fp_examples[:8]))
    if fn_examples:
        print("  Пропуски (II род):          ", ", ".join(fn_examples[:8]))


if __name__ == "__main__":
    if "--metrics" in sys.argv:
        metrics()
    else:
        build()
