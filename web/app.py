"""Мок-бэкенд FastAPI: рабочее место координатора + авто-уведомления пациенту.

Запуск:
    python -m uvicorn web.app:app --reload --port 8000
(из корня папки sm_case)
"""
from __future__ import annotations

import io
import os
import zipfile
from xml.etree import ElementTree as ET

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .store import STORE
from app.anonymize import anonymize

_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_text_from_bytes(data: bytes) -> str:
    """Извлекает текст из .docx (zip + document.xml), без сторонних библиотек."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    return "\n".join(
        "".join(t.text for t in p.iter(_NS + "t") if t.text) for p in root.iter(_NS + "p")
    ).strip()

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
DIST = os.path.join(os.path.dirname(HERE), "frontend", "dist")
USE_DIST = os.path.isfile(os.path.join(DIST, "index.html"))

app = FastAPI(title="СМ-Клиника — координатор маршрутов", version="0.1")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
if USE_DIST:
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")


class ActionIn(BaseModel):
    action: str


class AdvanceIn(BaseModel):
    hours: float = 24


class ResolveIn(BaseModel):
    decision: str  # confirm | reject


class AnalyzeIn(BaseModel):
    text: str
    protocol_id: str = "Загруженный протокол"
    study_type: str = ""


@app.get("/")
def index() -> FileResponse:
    # Если собран React (frontend/dist) — отдаём его; иначе старый ванильный интерфейс.
    if USE_DIST:
        return FileResponse(os.path.join(DIST, "index.html"))
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/meta")
def meta() -> dict:
    return STORE.meta()


@app.get("/api/routes")
def routes(status: str | None = None, urgent: bool | None = None,
           specialty: str | None = None, priority: str | None = None,
           role: str = "coordinator", q: str | None = None) -> dict:
    return {
        "now": STORE.now.isoformat(),
        "role": role,
        "routes": STORE.list_routes(
            status=status, urgent=urgent, specialty=specialty,
            priority=priority, role=role, q=q,
        ),
    }


@app.get("/api/llm/status")
def llm_status() -> dict:
    """Диагностика локальной LLM. Медицинский текст не выводится."""
    from app.llm_extractor import health

    return health()


@app.get("/api/routes/{rid}")
def route(rid: str) -> dict:
    r = STORE.get(rid)
    if r is None:
        raise HTTPException(404, "route not found")
    return r


@app.post("/api/routes/{rid}/action")
def action(rid: str, body: ActionIn) -> dict:
    r = STORE.act(rid, body.action)
    if r is None:
        raise HTTPException(404, "route not found")
    return r


@app.post("/api/simulate/advance")
def advance(body: AdvanceIn) -> dict:
    return STORE.advance(body.hours)


@app.get("/api/dashboard")
def dashboard() -> dict:
    return STORE.dashboard()


@app.get("/api/reviews")
def reviews(status: str | None = "pending") -> dict:
    return {"reviews": STORE.list_reviews(status=status), "now": STORE.now.isoformat()}


@app.get("/api/normals")
def normals() -> dict:
    return {"normals": STORE.list_normals(), "now": STORE.now.isoformat()}


@app.post("/api/reviews/{rid}/resolve")
def resolve_review(rid: str, body: ResolveIn) -> dict:
    if body.decision not in ("confirm", "reject"):
        raise HTTPException(400, "decision must be confirm or reject")
    res = STORE.resolve_review(rid, body.decision)
    if res is None:
        raise HTTPException(404, "review not found")
    return res


@app.post("/api/analyze")
def analyze(body: AnalyzeIn) -> dict:
    """Принимает текст протокола -> находки + маршрут (контракт docs/api_contract.md).

    Текст предварительно обезличивается: персональные данные не сохраняются.
    """
    text, removed = anonymize(body.text)
    res = STORE.ingest(text, body.protocol_id, body.study_type)
    res["anonymized"] = removed
    return res


@app.post("/api/analyze-file")
async def analyze_file(file: UploadFile = File(...)) -> dict:
    """Принимает файл протокола (.docx или .txt) -> находки + маршрут.

    Это и есть «протокол Word на входе — JSON на выходе».
    """
    data = await file.read()
    name = file.filename or "protocol"
    if name.lower().endswith(".docx"):
        text = docx_text_from_bytes(data)
    else:
        text = data.decode("utf-8", "replace")
    text, removed = anonymize(text)  # обезличивание до сохранения и анализа
    res = STORE.ingest(text, name)
    res["anonymized"] = removed
    return res


# Отдача собранного интерфейса (React): logo.svg, favicon и прочие файлы сборки.
if USE_DIST:
    app.mount("/", StaticFiles(directory=DIST, html=True), name="dist")
