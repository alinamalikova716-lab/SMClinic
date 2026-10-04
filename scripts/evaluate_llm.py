"""Сравнение rule-based находок и фактов локальной LLM (shadow-режим).

Запуск (нужны Ollama, модель и USE_LLM=true):
    python scripts/evaluate_llm.py

Скрипт не меняет маршруты — только показывает расхождения RULE != LLM.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.llm_extractor import extract_facts_llm, health  # noqa: E402
from app.processor import load_rules, extract, dedupe  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTOCOLS = os.path.join(HERE, "data", "protocols.jsonl")

RULE_TO_LLM = {"trigger": "present", "negated": "negated", "uncertain": "uncertain"}


def main() -> None:
    state = health()
    print("LLM:", state)
    if not (state.get("enabled") and state.get("available")):
        print("Ollama недоступна или USE_LLM=false — сравнение не выполняется.")
        return

    triggers, _routing, uncertainty = load_rules()
    with open(PROTOCOLS, encoding="utf-8") as fh:
        protocols = [json.loads(line) for line in fh]
    limit = int(os.environ.get("LLM_EVAL_LIMIT", "0") or 0)
    if limit:
        protocols = protocols[:limit]
        print(f"Ограничение выборки: {limit} протоколов (LLM_EVAL_LIMIT)")

    stats = Counter()
    print()
    print(f"{'протокол':<38} {'rule':<22} {'llm':<22} {'status':<8} evidence")
    print("-" * 100)
    for proto in protocols:
        rule_findings = dedupe(extract(proto["text"], triggers, uncertainty))
        try:
            llm = extract_facts_llm(proto["text"], protocol_id=proto["id"])
        except Exception as exc:  # noqa: BLE001
            stats["llm_error"] += 1
            print(f"{proto['id'][:37]:<38} ошибка LLM: {type(exc).__name__}")
            continue

        rule_by = {f.title.lower(): f.status for f in rule_findings}
        llm_by = {f["name"].lower(): f["status"] for f in llm["findings"]}
        names = sorted(set(rule_by) | set(llm_by))
        for n in names:
            r = rule_by.get(n, "—")
            l = llm_by.get(n, "—")
            match = "ok" if RULE_TO_LLM.get(r) == l or r == "—" or l == "—" else "DIFF"
            if match == "DIFF":
                stats["disagreement"] += 1
            stats["findings"] += 1
        if any(RULE_TO_LLM.get(rule_by.get(n)) != llm_by.get(n) for n in names):
            for n in names:
                r = rule_by.get(n, "—")
                l = llm_by.get(n, "—")
                if RULE_TO_LLM.get(r) != l and r != "—" and l != "—":
                    print(f"{proto['id'][:37]:<38} {n[:21]:<22} {n[:21]:<22} "
                          f"{'RULE!=LLM':<8}")

    print()
    print("Итого:", dict(stats))


if __name__ == "__main__":
    main()
