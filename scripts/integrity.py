"""Защита проекта от параллельных правок.

Команды:
    python scripts/integrity.py freeze   # зафиксировать текущие правила и ядро
    python scripts/integrity.py check    # проверить, не изменилось ли что-то
    python scripts/integrity.py lock     # запретить запись в критичные файлы (read-only)
    python scripts/integrity.py unlock   # снять запрет

Замораживаются файлы, от которых зависят результаты распознавания:
rules/*.json и ядро (app/processor.py, web/app.py, web/store.py).
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULESET = os.path.join(HERE, "rules", "ruleset.json")

TARGETS = [
    "rules/triggers.json",
    "rules/routing.json",
    "rules/uncertainty.json",
    "app/processor.py",
    "web/app.py",
    "web/store.py",
]


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def _targets() -> list[str]:
    return [t for t in TARGETS if os.path.exists(os.path.join(HERE, t))]


def freeze() -> None:
    files = {t: _sha(os.path.join(HERE, t)) for t in _targets()}
    combined = hashlib.sha256("".join(f"{k}:{v}" for k, v in sorted(files.items())).encode()).hexdigest()[:12]
    triggers = json.load(open(os.path.join(HERE, "rules", "triggers.json"), encoding="utf-8"))
    data = {
        "version": triggers.get("version", "?"),
        "findings": len(triggers.get("findings", [])),
        "frozen_at": datetime.now().isoformat(timespec="seconds"),
        "checksum": combined,
        "files": files,
    }
    with open(RULESET, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"Версия зафиксирована: правила v{data['version']}, находок {data['findings']}, checksum {combined}")


def check() -> int:
    if not os.path.exists(RULESET):
        print("Нет снимка. Сначала: python scripts/integrity.py freeze")
        return 1
    snap = json.load(open(RULESET, encoding="utf-8"))
    changed = []
    for path, old in snap["files"].items():
        full = os.path.join(HERE, path)
        if not os.path.exists(full):
            changed.append(f"{path} — УДАЛЁН")
        elif _sha(full) != old:
            changed.append(f"{path} — ИЗМЕНЁН")
    print(f"Зафиксировано: правила v{snap['version']} ({snap['frozen_at']}), checksum {snap['checksum']}")
    if changed:
        print("ВНИМАНИЕ, файлы изменились после заморозки:")
        for c in changed:
            print("  !", c)
        return 2
    print("OK: правила и ядро не менялись.")
    return 0


def _set_readonly(readonly: bool) -> None:
    for t in _targets():
        full = os.path.join(HERE, t)
        mode = os.stat(full).st_mode
        if readonly:
            os.chmod(full, mode & ~stat.S_IWRITE)
        else:
            os.chmod(full, mode | stat.S_IWRITE)
    state = "только чтение" if readonly else "запись разрешена"
    print(f"Критичные файлы: {state} ({len(_targets())} шт.)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "freeze":
        freeze()
    elif cmd == "check":
        sys.exit(check())
    elif cmd == "lock":
        _set_readonly(True)
    elif cmd == "unlock":
        _set_readonly(False)
    else:
        print("Команды: freeze | check | lock | unlock")
