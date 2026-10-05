"""Обезличивание текста протокола перед сохранением и анализом.

Скрываем только ФИО пациента - остальные данные (даты, врач, контакты)
не трогаем. Клиническая часть не затрагивается.

Использование:
    from app.anonymize import anonymize
    clean, removed = anonymize(text)
"""
from __future__ import annotations

import re

# Значение обрезается по концу предложения, переносу или следующей метке ФИО,
# чтобы не «съесть» клинический текст, даже если он в одну строку.
_RULES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"((?:ФИО[^\n:]{0,40}|Пациент)\s*:\s*).{0,80}?(?=\.\s|\n|$|\s*(?:ФИО|Пациент)\s*:)",
            re.I,
        ),
        r"\1[скрыто]",
    ),
]


def anonymize(text: str) -> tuple[str, int]:
    """Возвращает (очищенный текст, число сработавших замен)."""
    if not text:
        return text, 0
    removed = 0
    clean = text
    for pattern, repl in _RULES:
        clean, n = pattern.subn(repl, clean)
        removed += n
    return clean, removed #
