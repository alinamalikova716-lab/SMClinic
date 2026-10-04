import { STATUS_LABELS } from "../lib/util.js";

const COLORS = [
  "#13ab7b", "#26608f", "#fe8b4b", "#8a6100", "#41d6bd",
  "#7a5af8", "#e5484d", "#2ea56b", "#5a6675", "#d48fb0",
  "#3f8fbf", "#b08d57",
];

// Круговая (кольцевая) диаграмма на SVG, с легендой и процентами.
function PieChart({ data }) {
  const entries = Object.entries(data)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  if (!total) return <div className="upl-empty">Нет данных</div>;

  const R = 70;
  const C = 2 * Math.PI * R;
  let offset = 0;

  return (
    <div className="pie-wrap">
      <svg viewBox="0 0 200 200" className="pie-svg" role="img" aria-label="Маршруты по специальностям">
        <circle cx="100" cy="100" r={R} fill="none" stroke="#eef2f7" strokeWidth="28" />
        {entries.map(([label, value], i) => {
          const len = (value / total) * C;
          const seg = (
            <circle
              key={label}
              cx="100"
              cy="100"
              r={R}
              fill="none"
              stroke={COLORS[i % COLORS.length]}
              strokeWidth="28"
              strokeDasharray={`${len} ${C - len}`}
              strokeDashoffset={-offset}
              transform="rotate(-90 100 100)"
            />
          );
          offset += len;
          return seg;
        })}
        <text x="100" y="96" textAnchor="middle" className="pie-total">{total}</text>
        <text x="100" y="116" textAnchor="middle" className="pie-caption">маршрутов</text>
      </svg>

      <div className="pie-legend">
        {entries.map(([label, value], i) => (
          <div className="pl-row" key={label}>
            <span className="pl-dot" style={{ background: COLORS[i % COLORS.length] }} />
            <span className="pl-label">{label || "—"}</span>
            <span className="pl-val">{value}</span>
            <span className="pl-pct">{Math.round((value / total) * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Bars({ data, labelMap }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map((e) => e[1]));
  return (
    <div className="bars">
      {entries.map(([k, v]) => (
        <div className="b-row" key={k}>
          <span className="b-label">{labelMap ? labelMap[k] || k : k || "—"}</span>
          <span className="b-track">
            <span className="b-fill" style={{ width: `${(v / max) * 100}%` }} />
          </span>
          <span className="b-val">{v}</span>
        </div>
      ))}
    </div>
  );
}

export default function Dashboard({ data }) {
  if (!data) return <div className="empty">Загрузка…</div>;
  const base = data.protocols_total || data.total || 1;
  return (
    <>
      <div className="dash-cards">
        <div className="stat">
          <div className="v">{data.total}</div>
          <div className="l">Маршрутов создано</div>
        </div>
        <div className="stat urgent">
          <div className="v">{data.urgent}</div>
          <div className="l">Срочных находок</div>
        </div>
        <div className="stat">
          <div className="v">{data.booked_count || 0}</div>
          <div className="l">Записались</div>
        </div>
        <div className="stat">
          <div className="v">{data.visit_count || 0}</div>
          <div className="l">Приём состоялся</div>
        </div>
      </div>

      <div className="dash-grid">
        <div className="panel">
          <h3>Статистика</h3>
          <div className="funnel">
            {data.funnel.map((f, i) => {
              // «Выявлена значимая находка» — от всех протоколов,
              // остальные этапы — от количества триггеров (найденных находок).
              const denom = i === 0 ? base : data.total || 1;
              const pct = Math.min(100, Math.round((f.value / denom) * 100));
              return (
                <div className="f-row" key={f.label}>
                  <div className="f-top">
                    <span>{f.label}</span>
                    <span>
                      <b>{f.value}</b> · {pct}%
                    </span>
                  </div>
                  <div className="f-track">
                    <div className="f-fill" style={{ width: `${pct}%` }}>
                      {pct > 12 ? pct + "%" : ""}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="panel">
          <h3>Маршруты по специальностям</h3>
          <PieChart data={data.by_specialty} />
          <h3 style={{ marginTop: 24 }}>Статусы</h3>
          <Bars data={data.by_status} labelMap={STATUS_LABELS} />
        </div>
      </div>
    </>
  );
}
