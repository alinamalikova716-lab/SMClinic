"""Тесты модуля извлечения фактов LLM.

Проверки, не требующие модели, выполняются всегда. Сценарии с Qwen запускаются,
только если Ollama доступна и USE_LLM=true — иначе помечаются как пропущенные.

    python scripts/test_llm.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.llm_extractor import evidence_is_valid, health  # noqa: E402

ok = True


def check(name, cond):
    global ok
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        ok = False


print("Проверки без модели:")
check("evidence совпадает с текстом", evidence_is_valid("узел 24 мм", "Определяется узел 24 мм."))
check("подделанная evidence отклоняется", not evidence_is_valid("узел 99 мм", "Определяется узел 24 мм."))
check("evidence с другими пробелами принимается",
      evidence_is_valid("узел   24  мм", "Определяется узел 24 мм."))

print()
state = health()
print("Состояние LLM:", state)
if not (state.get("enabled") and state.get("available")):
    print()
    print("Сценарии с Qwen пропущены: Ollama недоступна или USE_LLM=false.")
    print("Для полного прогона: USE_LLM=true LLM_MODE=shadow и ollama pull qwen3:8b")
else:
    from app.llm_extractor import extract_facts_llm

    cases = [
        ("конкременты не выявлены", "Конкременты не выявлены.", "negated", None),
        ("миома 24 мм", "Определяется миоматозный узел 24 мм.", "present", 24.0),
        ("нельзя исключить", "Нельзя исключить образование правой молочной железы.", "uncertain", None),
        ("BI-RADS 2", "BI-RADS 2.", None, None),
        ("BI-RADS 4", "BI-RADS 4.", None, None),
        ("дисклеймер", "Заключение не является диагнозом.", None, None),
        ("без признаков роста", "Миома без признаков роста.", "present", None),
        ("норма", "Патологии не выявлено.", None, None),
    ]
    print()
    print("Сценарии с Qwen:")
    for name, text, want_status, want_size in cases:
        try:
            res = extract_facts_llm(text, protocol_id=name)
            findings = res["findings"]
            if want_status is None:
                good = True  # не должны выдумывать патологию/специалиста
            else:
                good = any(f["status"] == want_status for f in findings)
            if want_size is not None:
                good = good and any((f.get("size_mm") or 0) == want_size for f in findings)
            check(f"{name}: {[f['status'] for f in findings]}", good)
        except Exception as exc:  # noqa: BLE001
            check(f"{name}: ошибка {type(exc).__name__}", False)

print()
print("ИТОГ:", "все проверки пройдены" if ok else "есть ошибки")
sys.exit(0 if ok else 1)
