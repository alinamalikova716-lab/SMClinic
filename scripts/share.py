"""Архив проекта для передачи команде / на защиту.

Включает код, правила, данные и УЖЕ СОБРАННЫЙ интерфейс (frontend/dist),
чтобы получателю не требовался Node.js — достаточно Python.

    python scripts/share.py
Результат: dist/sm_case_share_<дата_время>.zip
"""
from __future__ import annotations

import os
import zipfile
from datetime import datetime

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(HERE, "dist")

INCLUDE_DIRS = ["app", "web", "rules", "scripts", "docs", "schemas", "data",
                "frontend/src", "frontend/dist", "materials/protocols"]
INCLUDE_FILES = ["start.bat", "README.md", "requirements.txt",
                 "frontend/package.json", "frontend/vite.config.js", "frontend/index.html"]
SKIP_PARTS = {"node_modules", "__pycache__", ".vite"}
SKIP_PREFIX = ("_backup",)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(OUT_DIR, f"sm_case_share_{stamp}.zip")
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in INCLUDE_FILES:
            full = os.path.join(HERE, rel)
            if os.path.isfile(full):
                z.write(full, rel)
                count += 1
        for d in INCLUDE_DIRS:
            base = os.path.join(HERE, d)
            for dirpath, dirnames, files in os.walk(base):
                dirnames[:] = [x for x in dirnames if x not in SKIP_PARTS and not x.startswith(SKIP_PREFIX)]
                for name in files:
                    full = os.path.join(dirpath, name)
                    rel = os.path.relpath(full, HERE)
                    parts = rel.split(os.sep)
                    if any(p in SKIP_PARTS or p.startswith(SKIP_PREFIX) for p in parts):
                        continue
                    z.write(full, rel)
                    count += 1
    size = os.path.getsize(out)
    print(f"Архив для передачи: {out}")
    print(f"Файлов: {count} | размер: {size/1024/1024:.1f} МБ")


if __name__ == "__main__":
    main()
