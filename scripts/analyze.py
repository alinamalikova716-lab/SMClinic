"""Прогоняет движок извлечения триггеров по всем протоколам и строит сводку.

Использование:
    python scripts/analyze.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from app.processor import CLINICAL_RISK_SHARE_LIMIT, load_rules, process  # noqa: E402

DATA = os.path.join(HERE, "data")
IN = os.path.join(DATA, "protocols.jsonl")
OUT = os.path.join(DATA, "analysis.jsonl")


def main() -> None:
    triggers, routing, uncertainty = load_rules()
    with open(IN, encoding="utf-8") as fh:
        protocols = [json.loads(line) for line in fh]

    results = []
    per_finding = Counter()
    per_category_trigger = Counter()
    per_category_total = Counter()
    per_uncertain = Counter()
    examples: dict[str, str] = {}

    for proto in protocols:
        res = process(proto["text"], triggers, routing, uncertainty)
        results.append({**proto, "analysis": res})
        per_category_total[proto["category"]] += 1
        if res["is_trigger"]:
            per_category_trigger[proto["category"]] += 1
        for f in res["triggers"]:
            per_finding[f"{f['title']}"] += 1
            examples.setdefault(f["id"], proto["id"])
        for f in res["uncertain"]:
            per_uncertain[f"{f['title']}"] += 1

    # Guard от шума: если пометок «клинический риск» больше порога — снимаем их.
    total = len(results)
    clinical_prots = {
        r["id"] for r in results
        if any(f.get("flag") == "clinical" for f in r["analysis"]["uncertain"])
    }
    if total and len(clinical_prots) / total > CLINICAL_RISK_SHARE_LIMIT:
        print(f"ВНИМАНИЕ: пометок 'клинический риск' {len(clinical_prots)} "
              f"({len(clinical_prots) / total:.0%}) > порога {CLINICAL_RISK_SHARE_LIMIT:.0%} — сняты как шум")
        for rec in results:
            an = rec["analysis"]
            for f in an["findings"]:
                if f.get("flag") == "clinical":
                    f["status"], f["flag"], f["issue"] = "trigger", "", ""
            an["uncertain"] = [f for f in an["uncertain"] if f.get("flag") != "clinical"]
            an["reviews"] = [rv for rv in an["reviews"] if rv["finding"].get("flag") != "clinical"]

    per_uncertain = Counter()
    for rec in results:
        for f in rec["analysis"]["uncertain"]:
            per_uncertain[f["title"]] += 1

    with open(OUT, "w", encoding="utf-8") as fh:
        for rec in results:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Протоколов всего: {len(protocols)}")
    print(f"Сработал триггер: {sum(1 for r in results if r['analysis']['is_trigger'])}")
    print()
    print("По категориям (триггер / всего):")
    for cat in sorted(per_category_total):
        print(f"  {cat:<40} {per_category_trigger[cat]:>3} / {per_category_total[cat]:<3}")
    print()
    print("Найденные триггеры (положительные срабатывания):")
    for name, n in per_finding.most_common():
        print(f"  {n:>3}  {name}")
    print()
    print("Требуют уточнения (uncertain — маршрут не создаётся автоматически):")
    if per_uncertain:
        for name, n in per_uncertain.most_common():
            print(f"  {n:>3}  {name}")
    else:
        print("  нет")
    print()
    print("Примеры:")
    for fid, pid in examples.items():
        print(f"  {fid:<28} -> {pid}")


if __name__ == "__main__":
    main()
