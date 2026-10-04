import { useState } from "react";
import { splitProtocol } from "../lib/util.js";

// Раздел «Требует уточнения»: находка есть в описательной части протокола,
// но отсутствует в заключении — вероятно, автор протокола ошибся.
// Маршрут и пуш пациенту уже созданы — здесь только пометка для координатора.
export default function Reviews({ reviews, onResolve, pLabel }) {
  const [openProtocol, setOpenProtocol] = useState(null);

  if (!reviews.length) {
    return <div className="empty" style={{ padding: 40 }}>Нет находок, требующих уточнения</div>;
  }
  return (
    <div className="audit-wrap">
      <div className="audit-head">
        <h2>Требует уточнения</h2>
        <div className="sub">
          Два независимых случая: <b>ошибка оформления</b> (нет заключения, диагноза и
          рекомендации) и <b>находка не вынесена в заключение</b>. Пациенту уведомление
          уже отправлено, маршрут создан; здесь фиксируется причина для проверки.
        </div>
      </div>

      {reviews.map((rv) => {
        const sr = rv.suggested_route || {};
        return (
          <div className="review-card" key={rv.id}>
            <div className="rc-head">
              <span className="prio prio-urgent">
                {rv.finding.flag === "structure" ? "Ошибка оформления" : "Находка не в заключении"}
              </span>
              <b>{rv.id}</b>
              <span className="rc-pat">
                пациент {rv.patient?.id}
                {rv.patient?.age ? `, ${rv.patient.age} лет` : ""}
              </span>
              <span className="rc-study">
                {rv.source?.study} · {rv.source?.date?.slice(0, 10)}
              </span>
            </div>

            <div className="rc-body">
              <div className="rc-left">
                <div className="rc-finding-title">{rv.finding.title}</div>
                <div className="rc-marker">
                  {rv.finding.issue || "Находка не вынесена в заключение"}
                </div>
                <div className="rc-evidence">«{rv.finding.evidence}»</div>

                {sr.specialist && (
                  <div className="rc-suggest">
                    Маршрут уже создан: <b>{sr.specialist}</b> · {sr.next_step}
                    {sr.priority ? ` · ${pLabel(sr.priority)}` : ""}. Уведомление пациенту отправлено.
                  </div>
                )}

                {rv.protocol_text && (
                  <button
                    className="btn protocol-btn"
                    onClick={() => setOpenProtocol({ title: rv.finding.title, text: rv.protocol_text })}
                  >
                    Открыть полный протокол
                  </button>
                )}
              </div>

              <div className="rc-actions">
                <button className="btn primary" onClick={() => onResolve(rv.id, "confirm")}>
                  Снять пометку
                </button>
                <button className="btn danger" onClick={() => onResolve(rv.id, "reject")}>
                  Отклонить
                </button>
              </div>
            </div>
          </div>
        );
      })}

      {openProtocol && (
        <div className="modal-backdrop" onClick={() => setOpenProtocol(null)}>
          <div className="modal protocol-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2>Протокол исследования</h2>
              <button className="modal-x" onClick={() => setOpenProtocol(null)}>×</button>
            </div>
            <div className="protocol-sub">Находка: {openProtocol.title}</div>
            <div className="protocol-body">
              {splitProtocol(openProtocol.text).map((b, i) =>
                b.header ? (
                  <div className="pb-head" key={i}>{b.text}</div>
                ) : (
                  <p key={i}>{b.text}</p>
                )
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
