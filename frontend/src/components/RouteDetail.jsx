import { useState } from "react";
import { fmtDate, isOverdue, STATUS_LABELS } from "../lib/util.js";
import PushPreview from "./PushPreview.jsx";
import ProtocolModal from "./ProtocolModal.jsx";

// Подсветка подстроки-триггера внутри цитаты (без dangerouslySetInnerHTML).
function Highlight({ evidence, match }) {
  if (!match || !evidence.includes(match)) return <>{evidence}</>;
  const i = evidence.indexOf(match);
  return (
    <>
      {evidence.slice(0, i)}
      <mark>{match}</mark>
      {evidence.slice(i + match.length)}
    </>
  );
}

export default function RouteDetail({ route, meta, now, onAction, onRollback, pLabel }) {
  const [openProtocol, setOpenProtocol] = useState(null);
  if (!route) return <section className="detail"><div className="empty">Выберите маршрут слева</div></section>;

  const overdue = isOverdue(route, now);
  const actions = [
    { key: route.next_action, label: meta?.action_labels?.[route.next_action] || "Продвинуть маршрут", cls: "btn primary" },
    { key: "resend", label: "Повторить уведомление", cls: "btn" },
    { key: "call", label: "Задача на обзвон", cls: "btn" },
    { key: "no_show", label: "Неявка", cls: "btn danger" },
    { key: "not_engaged", label: "Не вовлечён", cls: "btn danger" },
  ];

  return (
    <section className="detail">
      <div className="d-head">
        <div>
          <h2>
            {route.id} · пациент {route.patient.id}
          </h2>
          <div className="sub">
            {route.patient.sex === "Ж" ? "жен." : "муж."}
            {route.patient.age ? `, ${route.patient.age} лет` : ""} · {route.study} · {fmtDate(route.date)}
          </div>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          <span className={"prio prio-" + route.priority}>{pLabel(route.priority)}</span>
          {overdue && <span className="badge urgent">просрочено</span>}
          <span className="badge ok">{STATUS_LABELS[route.status] || route.status}</span>
          <button className="btn" onClick={onRollback} title="Вернуть пациента на предыдущий этап">
            ↶ Вернуть предыдущий этап
          </button>
        </div>
      </div>

      <div className="d-grid">
        <div>
          <div className="panel">
            <h3>
              Клинически значимая находка
            </h3>
            {route.triggers.map((f, i) => (
              <div key={i} className={"trigger" + (f.severity === "urgent" ? " urgent" : "")}>
                <div className="t-domain">{f.domain}</div>
                <div className="t-title">{f.title}</div>
                {f.status === "uncertain" && (
                  <div className="t-issue">
                    Требует уточнения: {f.issue || "находка не вынесена в заключение"}
                  </div>
                )}
                <div className="evidence">
                  «<Highlight evidence={f.evidence} match={f.match} />»
                </div>
                <div className="attrs">
                  {Object.entries(f.attributes || {}).map(([k, v]) => (
                    <span className="attr" key={k}>
                      {k}: {String(v)}
                    </span>
                  ))}
                  <span className="attr conf">уверенность {Math.round((f.confidence || 0) * 100)}%</span>
                  <span className="attr conf">правило v{f.rule_version}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="panel">
            <h3>
              Рекомендованный маршрут
            </h3>
            <div className="route-box">
              <div className="rp-first">
                <span className={"prio prio-" + route.priority}>{pLabel(route.priority)}</span>
                <span className="rp-why">{route.priority_reason}</span>
              </div>
              <div className="rspec">{route.specialist}</div>
              <div className="rstep">{route.next_step}</div>
              {route.planned_step && <div className="rstep">Далее: {route.planned_step}</div>}
              <div className="rtarget">
                Целевой срок: <b>{route.target_days} дн.</b> · Подразделение: <b>{route.department}</b>
              </div>
            </div>
          </div>

          <div className="panel">
            <h3>
              Маршрут пациента {route.surgical === false && <span className="hint">— без госпитализации</span>}
            </h3>
            <ul className="steps">
              {route.steps.map((s) => (
                <li key={s.code} className={s.state}>
                  {s.label}
                </li>
              ))}
            </ul>
          </div>

          {route.protocol_text && (
            <div className="panel">
              <h3>Полный протокол исследования</h3>
              <button className="btn protocol-btn" onClick={() => setOpenProtocol(route.protocol_text)}>
                Открыть полный протокол
              </button>
            </div>
          )}

          <div className="panel">
            <h3>Действия координатора</h3>
            {route.tasks.map((t, i) => (
              <div className="task" key={i}>
                Задача: {t.label} — {t.owner}
              </div>
            ))}
            <div className="actions">
              {actions.map((a) => (
                <button key={a.key} className={a.cls} onClick={() => onAction(a.key)}>
                  {a.label}
                </button>
              ))}
              <button className="btn" onClick={onRollback}>
                ↶ Вернуть предыдущий этап
              </button>
            </div>
          </div>
        </div>

        <div>
          <PushPreview text={route.notification_text} />

          <div className="panel">
            <h3>Уведомления пациенту</h3>
            <ul className="log">
              {route.notifications.length === 0 && <li>Пока нет</li>}
              {route.notifications.map((n, i) => (
                <li key={i}>
                  <span className="when">{fmtDate(n.at)}</span> · {n.channel}
                  <br />
                  {n.label}
                </li>
              ))}
            </ul>
          </div>

          <div className="panel">
            <h3>
              История событий
            </h3>
            <ul className="log">
              {route.history.map((h, i) => (
                <li key={i}>
                  <span className="when">{fmtDate(h.at)}</span> · {h.label}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {openProtocol && (
        <ProtocolModal
          title={route.triggers[0]?.title}
          text={openProtocol}
          onClose={() => setOpenProtocol(null)}
        />
      )}
    </section>
  );
}
