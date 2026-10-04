// Протоколы без значимых находок. Сохраняем всё, чтобы пациент «не потерялся»
// и всегда можно было доказать, что по исследованию триггера не было.
export default function Normals({ normals }) {
  if (!normals.length) {
    return <div className="empty" style={{ padding: 40 }}>Записей «без патологий» пока нет</div>;
  }
  return (
    <div className="audit-wrap">
      <div className="audit-head">
        <h2>Без патологий</h2>
        <div className="sub">
          Исследования без клинически значимых находок. Маршрут не создаётся,
          но заключение сохранено.
        </div>
      </div>

      {normals.map((n) => (
        <div className="normal-card" key={n.id}>
          <div className="nc-head">
            <span className="prio prio-watch">Без патологий</span>
            <b>{n.id}</b>
            <span className="rc-pat">
              пациент {n.patient?.id}
              {n.patient?.age ? `, ${n.patient.age} лет` : ""}
            </span>
            <span className="rc-study">
              {n.source?.study} · {n.source?.date?.slice(0, 10)}
            </span>
          </div>
          <div className="nc-concl">{n.conclusion}</div>
          {n.protocol_text && (
            <details className="rc-protocol">
              <summary>Полный протокол исследования</summary>
              <pre>{n.protocol_text}</pre>
            </details>
          )}
        </div>
      ))}
    </div>
  );
}
