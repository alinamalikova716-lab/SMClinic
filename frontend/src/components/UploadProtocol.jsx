import { useRef, useState } from "react";
import { analyzeFile } from "../api.js";

const STATUS_RU = {
  trigger: "Подтверждено",
  uncertain: "Требует уточнения",
  negated: "Отрицается",
};

export default function UploadProtocol({ open, onClose, onCreated, onProcessed }) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const inputRef = useRef(null);

  if (!open) return null;

  const send = async (file) => {
    if (!file) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await analyzeFile(file);
      setResult(data);
      onProcessed?.();
    } catch (e) {
      setError("Не удалось обработать файл: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  const firstRoute = result?.created_routes?.[0] || null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Загрузить протокол исследования</h2>
          <button className="modal-x" onClick={onClose}>×</button>
        </div>

        {!result && (
          <>
            <div
              className={"dropzone" + (dragging ? " active" : "")}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); send(e.dataTransfer.files?.[0]); }}
              onClick={() => inputRef.current?.click()}
            >
              <div className="dz-icon">📄</div>
              <div className="dz-title">Перетащите протокол сюда</div>
              <div className="dz-sub">формат Word (.docx) или текст (.txt)</div>
              <button className="btn primary" style={{ marginTop: 14 }}>Выбрать файл</button>
              <input
                ref={inputRef}
                type="file"
                accept=".docx,.txt"
                style={{ display: "none" }}
                onChange={(e) => send(e.target.files?.[0])}
              />
            </div>
            <div className="upl-note">
              Система сама найдёт клинически значимые находки, определит срочность и специалиста,
              сформирует маршрут и подготовит уведомление пациенту — без диагноза.
            </div>
          </>
        )}

        {loading && <div className="upl-loading">Анализируем протокол…</div>}
        {error && <div className="upl-error">{error}</div>}

        {result && (
          <div className="upl-result">
            <div className="upl-file">
              <b>{result.study?.type || "Протокол"}</b>
              <span>{result.protocol_id}</span>
            </div>

            {result.anonymized > 0 && (
              <div className="upl-anon">
                ФИО пациента скрыто (замен: {result.anonymized})
              </div>
            )}

            <h4>Найденные находки</h4>
            {result.findings.length === 0 && <div className="upl-empty">Значимых находок не обнаружено.</div>}
            {result.findings.map((f, i) => (
              <div className={"upl-finding st-" + f.status} key={i}>
                <div className="upl-f-top">
                  <span className={"upl-badge st-" + f.status}>{STATUS_RU[f.status] || f.status}</span>
                  <b>{f.title}</b>
                </div>
                <div className="upl-f-ev">«{f.evidence}»</div>
                {f.marker && <div className="upl-f-marker">Маркер сомнения: «{f.marker}»</div>}
                {f.attributes && Object.keys(f.attributes).length > 0 && (
                  <div className="upl-f-attrs">
                    {Object.entries(f.attributes).map(([k, v]) => (
                      <span className="attr" key={k}>{k}: {String(v)}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {result.created_routes.length > 0 && (
              <>
                <h4>Созданные маршруты</h4>
                {result.created_routes.map((r) => (
                  <div className="upl-route" key={r.id}>
                    <span className={"prio prio-" + r.priority}>{r.specialist}</span>
                    <span> · {r.next_step}</span>
                    <div className="upl-route-sub">срок {r.target_days} дн. · {r.department}</div>
                  </div>
                ))}
              </>
            )}

            {result.created_reviews.length > 0 && (
              <>
                <h4>Ушло в очередь «Требует уточнения»</h4>
                {result.created_reviews.map((rv) => (
                  <div className="upl-review" key={rv.id}>
                    {rv.finding.title} — маркер «{rv.finding.marker}»
                  </div>
                ))}
              </>
            )}

            {firstRoute && (
              <>
                <h4>Уведомление пациенту (без диагноза)</h4>
                <div className="upl-push">{firstRoute.notification_text}</div>
              </>
            )}

            {result.saved_to === "norm" && (
              <div className="upl-saved">Значимых находок нет — протокол сохранён в блок «Без клинических значимых триггеров».</div>
            )}

            <div className="upl-actions">
              <button className="btn" onClick={() => setResult(null)}>Загрузить ещё</button>
              {firstRoute && (
                <button className="btn primary" onClick={() => onCreated(firstRoute.id)}>
                  Открыть маршрут в очереди
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
