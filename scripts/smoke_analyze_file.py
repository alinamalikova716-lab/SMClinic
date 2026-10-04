"""Проверка живого потока: Word-протокол -> находки + маршрут.

Запуск (при поднятом FastAPI на 8000):
    python scripts/smoke_analyze_file.py
"""
import glob
import json
import os
import urllib.request

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "materials", "protocols")
URL = "http://127.0.0.1:8000/api/analyze-file"


def main() -> None:
    cands = glob.glob(os.path.join(BASE, "**", "*.docx"), recursive=True)
    if not cands:
        print("Протоколы .docx не найдены")
        return
    path = cands[0]
    data = open(path, "rb").read()

    boundary = "----smclinic"
    body = b"".join([
        ("--" + boundary + "\r\n").encode(),
        b'Content-Disposition: form-data; name="file"; filename="protocol.docx"\r\n',
        b"Content-Type: application/octet-stream\r\n\r\n",
        data,
        ("\r\n--" + boundary + "--\r\n").encode(),
    ])
    req = urllib.request.Request(
        URL, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        d = json.load(resp)

    print("Файл:", os.path.basename(path))
    print("POST /api/analyze-file ->", d["protocol_id"])
    for f in d["findings"]:
        print(f"   [{f['status']:<9}] {f['title']:<42} маркер={f.get('marker', '')}")
    print("   создано маршрутов:", len(d["created_routes"]), "| на уточнении:", len(d["created_reviews"]))
    for rt in d["created_routes"]:
        print("   ->", rt["specialist"], "| приоритет:", rt["priority"])


if __name__ == "__main__":
    main()
