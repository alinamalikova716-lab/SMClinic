"""Извлекает все протоколы УЗИ из .docx в единый JSONL.

Использование:
    python scripts/extract_protocols.py
"""
from __future__ import annotations

import json
import os
import zipfile
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "materials", "protocols")
OUT = os.path.join(HERE, "data", "protocols.jsonl")

NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_text(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    lines = []
    for p in root.iter(NS + "p"):
        lines.append("".join(t.text for t in p.iter(NS + "t") if t.text))
    return "\n".join(lines).strip()


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    records = []
    for dirpath, _dirs, files in os.walk(SRC):
        cat = os.path.basename(dirpath)
        if cat == "протоколы":
            continue
        for name in sorted(f for f in files if f.lower().endswith(".docx")):
            text = docx_text(os.path.join(dirpath, name))
            records.append(
                {
                    "id": f"{cat}/{name}",
                    "category": cat,
                    "file": name,
                    "text": text,
                }
            )
    with open(OUT, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Written {len(records)} protocols -> {OUT}")
    cats: dict[str, int] = {}
    for rec in records:
        cats[rec["category"]] = cats.get(rec["category"], 0) + 1
    for c, n in sorted(cats.items()):
        print(f"  {n:>3}  {c}")


if __name__ == "__main__":
    main()
