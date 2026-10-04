import { fmtDate, isOverdue, STATUS_LABELS } from "../lib/util.js";

export default function Queue({
  routes,
  currentId,
  onSelect,
  search,
  setSearch,
  priority,
  setPriority,
  specialty,
  setSpecialty,
  specialties,
  pLabel,
  now,
}) {
  const urgent = routes.filter((r) => r.priority === "emergency" || r.priority === "urgent").length;
  return (
    <aside className="queue">
      <div className="queue-head">
        <input
          type="search"
          placeholder="Поиск: пациент, исследование, находка"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="filters">
          <select value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="">Все приоритеты</option>
            <option value="emergency">Экстренно</option>
            <option value="urgent">Срочно</option>
            <option value="planned">Планово</option>
            <option value="watch">Наблюдение</option>
          </select>
          <select value={specialty} onChange={(e) => setSpecialty(e.target.value)}>
            <option value="">Все специальности</option>
            {specialties.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="queue-stats">
          Маршрутов: <b>{routes.length}</b> · срочных: <b>{urgent}</b>
        </div>
      </div>

      <ul className="route-list">
        {routes.length === 0 && <li className="empty" style={{ marginTop: 20 }}>Ничего не найдено</li>}
        {routes.map((r) => {
          const overdue = isOverdue(r, now);
          return (
            <li
              key={r.id}
              className={"route-item" + (currentId === r.id ? " active" : "")}
              onClick={() => onSelect(r.id)}
            >
              <div className="ri-top">
                <span className={"prio prio-" + r.priority}>{pLabel(r.priority)}</span>
                <span className="ri-id">
                  {r.id} · {r.patient.id}
                </span>
                <span className="ri-spec">{r.specialist}</span>
              </div>
              <div className="ri-trigger">{r.trigger}</div>
              <div className="ri-study">
                {r.study} · {fmtDate(r.date)}
              </div>
              <div className="ri-foot">
                <span className="badge">{STATUS_LABELS[r.status] || r.status}</span>
                <span className={overdue ? "overdue" : ""}>
                  {overdue ? "просрочено · " : "до "}
                  {fmtDate(r.due_at)}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
