const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

let META = { specialties: [], action_labels: {}, priorities: {} };
let LIST = [];
let CURRENT = null;
let NOW = null;

const PRIORITY_RU = { emergency: "Экстренно", urgent: "Срочно", planned: "Планово", watch: "Наблюдение" };
const pLabel = (p) => (META.priorities && META.priorities[p] ? META.priorities[p].label : PRIORITY_RU[p] || p);
const isOverdue = (r) =>
  NOW && r.due_at && new Date(r.due_at) < new Date(NOW) && !["closed", "not_engaged"].includes(r.status);

const STATUS_LABELS = {
  notification: "Уведомление отправлено",
  booked: "Записан",
  visit: "Приём состоялся",
  decision: "Тактика определена",
  hospital: "Направлен на госпитализацию",
  hospital_date: "Госпитализация назначена",
  operated: "Оперирован",
  followup: "Контроль назначен",
  closed: "Маршрут закрыт",
  no_show: "Неявка",
  not_engaged: "Не вовлечён",
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

function highlight(evidence, match) {
  if (!match) return esc(evidence);
  const i = evidence.indexOf(match);
  if (i < 0) return esc(evidence);
  return (
    esc(evidence.slice(0, i)) +
    "<mark>" + esc(match) + "</mark>" +
    esc(evidence.slice(i + match.length))
  );
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

const fmtDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
};

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._t);
  t._t = setTimeout(() => t.classList.remove("show"), 2600);
}

/* ---------------- routes list ---------------- */
async function loadMeta() {
  META = await api("/api/meta");
  const sel = $("#filter-specialty");
  META.specialties.forEach((s) => {
    const o = document.createElement("option");
    o.value = s; o.textContent = s;
    sel.appendChild(o);
  });
}

async function loadRoutes() {
  const params = new URLSearchParams();
  const q = $("#search").value.trim();
  if (q) params.set("q", q);
  const spec = $("#filter-specialty").value;
  if (spec) params.set("specialty", spec);
  const prio = $("#filter-priority").value;
  if (prio) params.set("priority", prio);
  const data = await api("/api/routes?" + params.toString());
  NOW = data.now;
  LIST = data.routes;
  renderList();
}

function renderList() {
  const ul = $("#route-list");
  ul.innerHTML = "";
  $("#queue-stats").innerHTML =
    `Маршрутов: <b>${LIST.length}</b> · срочных: <b>${LIST.filter((r) => r.urgent).length}</b>`;
  if (!LIST.length) {
    ul.innerHTML = `<li class="empty" style="margin-top:20px">Ничего не найдено</li>`;
    return;
  }
  for (const r of LIST) {
    const li = document.createElement("li");
    li.className = "route-item" + (CURRENT && CURRENT.id === r.id ? " active" : "");
    li.innerHTML = `
      <div class="ri-top">
        <span class="prio prio-${r.priority}">${esc(pLabel(r.priority))}</span>
        <span class="ri-id">${esc(r.id)} · ${esc(r.patient.id)}</span>
        <span class="ri-spec">${esc(r.specialist)}</span>
      </div>
      <div class="ri-trigger">${esc(r.trigger)}</div>
      <div class="ri-study">${esc(r.study)} · ${fmtDate(r.date)}</div>
      <div class="ri-foot">
        <span class="badge">${esc(STATUS_LABELS[r.status] || r.status)}</span>
        <span class="${isOverdue(r) ? "overdue" : ""}">${isOverdue(r) ? "просрочено · " : "до "}${fmtDate(r.due_at)}</span>
      </div>`;
    li.onclick = () => selectRoute(r.id);
    ul.appendChild(li);
  }
}

/* ---------------- detail ---------------- */
async function selectRoute(id) {
  CURRENT = await api("/api/routes/" + id);
  renderList();
  renderDetail();
}

function renderDetail() {
  const r = CURRENT;
  if (!r) return;
  const triggers = r.triggers
    .map((f) => {
      const attrs = Object.entries(f.attributes || {})
        .map(([k, v]) => `<span class="attr">${esc(k)}: ${esc(v)}</span>`)
        .join("");
      return `
        <div class="trigger ${f.severity === "urgent" ? "urgent" : ""}">
          <div class="t-domain">${esc(f.domain)}</div>
          <div class="t-title">${esc(f.title)}</div>
          <div class="evidence">«${highlight(f.evidence, f.match)}»</div>
          <div class="attrs">
            ${attrs}
            <span class="attr conf">уверенность ${(f.confidence * 100).toFixed(0)}%</span>
            <span class="attr conf">правило v${esc(f.rule_version)}</span>
          </div>
        </div>`;
    })
    .join("");

  const steps = r.steps
    .map((s) => `<li class="${s.state}">${esc(s.label)}</li>`)
    .join("");

  const notifs = (r.notifications || [])
    .map(
      (n) => `<li><span class="when">${fmtDate(n.at)}</span> · ${esc(n.channel)}<br>${esc(n.label)}</li>`
    )
    .join("") || "<li>Пока нет</li>";

  const hist = (r.history || [])
    .map((h) => `<li><span class="when">${fmtDate(h.at)}</span> · ${esc(h.label)}</li>`)
    .join("");

  const tasks = (r.tasks || [])
    .map((t) => `<div class="task">Задача: ${esc(t.label)} — ${esc(t.owner)}</div>`)
    .join("");

  const nextLabel = META.action_labels[r.next_action] || "Продвинуть маршрут";
  const actions = [
    `<button class="btn primary" data-act="${r.next_action}">${esc(nextLabel)}</button>`,
    `<button class="btn" data-act="resend">Повторить уведомление</button>`,
    `<button class="btn" data-act="call">Задача на обзвон</button>`,
    `<button class="btn danger" data-act="no_show">Неявка</button>`,
    `<button class="btn danger" data-act="not_engaged">Не вовлечён</button>`,
  ].join("");

  $("#detail").innerHTML = `
    <div class="d-head">
      <div>
        <h2>${esc(r.id)} · пациент ${esc(r.patient.id)}</h2>
        <div class="sub">${esc(r.patient.sex === "Ж" ? "жен." : "муж.")}${r.patient.age ? ", " + r.patient.age + " лет" : ""} ·
          ${esc(r.study)} · ${fmtDate(r.date)}</div>
      </div>
      <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
        <span class="prio prio-${r.priority}">${esc(pLabel(r.priority))}</span>
        ${isOverdue(r) ? '<span class="badge urgent">просрочено</span>' : ""}
        <span class="badge ok">${esc(STATUS_LABELS[r.status] || r.status)}</span>
      </div>
    </div>

    <div class="d-grid">
      <div>
        <div class="panel">
          <h3>Клинически значимая находка <span class="hint">— основание для маршрута</span></h3>
          ${triggers}
        </div>

        <div class="panel">
          <h3>Рекомендованный маршрут <span class="hint">— определяется правилами, а не «на глаз»</span></h3>
          <div class="route-box">
            <div class="rp-first">
              <span class="prio prio-${r.priority}">${esc(pLabel(r.priority))}</span>
              <span class="rp-why">${esc(r.priority_reason || "")}</span>
            </div>
            <div class="rspec">${esc(r.specialist)}</div>
            <div class="rstep">${esc(r.next_step)}</div>
            ${r.planned_step ? `<div class="rstep">Далее: ${esc(r.planned_step)}</div>` : ""}
            <div class="rtarget">Целевой срок: <b>${r.target_days} дн.</b> · Подразделение: <b>${esc(r.department)}</b></div>
          </div>
        </div>

        <div class="panel">
          <h3>Маршрут пациента</h3>
          <ul class="steps">${steps}</ul>
        </div>

        <div class="panel">
          <h3>Действия координатора</h3>
          ${tasks}
          <div class="actions">${actions}</div>
        </div>
      </div>

      <div>
        <div class="panel">
          <h3>Глазами пациента <span class="hint">— диагноз скрыт</span></h3>
          <div class="patient-preview">
            <div class="pp-head">
              <span class="pp-dot"></span>
              <span class="pp-title">Push · Личный кабинет</span>
              <span class="pp-note">отправлено автоматически</span>
            </div>
            <div class="pp-card">
              <div class="pp-app">СМ-Клиника · сейчас</div>
              <div class="pp-msg">${esc(r.notification_text)}</div>
              <div class="pp-buttons">
                <button class="pp-btn">Записаться к специалисту</button>
                <button class="pp-btn ghost">Онлайн-консультация</button>
                <button class="pp-btn ghost">Оставить заявку на звонок</button>
              </div>
            </div>
            <div class="pp-hide">В сообщении намеренно нет диагноза, названия болезни и результатов —
              только нейтральная рекомендация и безопасный следующий шаг.</div>
          </div>
        </div>

        <div class="panel">
          <h3>Уведомления пациенту</h3>
          <ul class="log">${notifs}</ul>
        </div>

        <div class="panel">
          <h3>История событий <span class="hint">— журнал «кто, что, когда»</span></h3>
          <ul class="log">${hist}</ul>
        </div>
      </div>
    </div>`;

  $$("#detail [data-act]").forEach((b) => {
    b.onclick = () => doAction(b.dataset.act);
  });
}

async function doAction(action) {
  if (!CURRENT) return;
  CURRENT = await api(`/api/routes/${CURRENT.id}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  toast(META.action_labels[action] || action);
  renderDetail();
  loadRoutes();
}

/* ---------------- model time ---------------- */
async function advance(hours) {
  const data = await api("/api/simulate/advance", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hours }),
  });
  $("#clock").textContent = fmtDate(data.now);
  toast(
    data.events.length
      ? `Прошло ${hours} ч · событий: ${data.events.length}`
      : `Прошло ${hours} ч · новых событий нет`
  );
  await loadRoutes();
  if (CURRENT) await selectRoute(CURRENT.id);
  if ($("#view-dashboard").classList.contains("active")) loadDashboard();
}

/* ---------------- dashboard ---------------- */
async function loadDashboard() {
  const d = await api("/api/dashboard");
  $("#clock").textContent = fmtDate(d.now);

  $("#dash-cards").innerHTML = `
    <div class="stat"><div class="v">${d.total}</div><div class="l">Маршрутов создано</div></div>
    <div class="stat urgent"><div class="v">${d.urgent}</div><div class="l">Срочных находок</div></div>
    <div class="stat"><div class="v">${d.by_status["booked"] || 0}</div><div class="l">Записались</div></div>
    <div class="stat"><div class="v">${d.by_status["followup"] || d.by_status["closed"] || 0}</div><div class="l">Дошли до контроля</div></div>`;

  const max = d.funnel[0]?.value || 1;
  $("#funnel").innerHTML = d.funnel
    .map((f) => {
      const pct = Math.round((f.value / max) * 100);
      return `<div class="f-row">
        <div class="f-top"><span>${esc(f.label)}</span><span><b>${f.value}</b> · ${pct}%</span></div>
        <div class="f-track"><div class="f-fill" style="width:${pct}%">${pct > 12 ? pct + "%" : ""}</div></div>
      </div>`;
    })
    .join("");

  const renderBars = (obj, el) => {
    const entries = Object.entries(obj).sort((a, b) => b[1] - a[1]);
    const m = Math.max(1, ...entries.map((e) => e[1]));
    $(el).innerHTML = entries
      .map(
        ([k, v]) => `<div class="b-row">
          <span class="b-label">${esc(k || "—")}</span>
          <span class="b-track"><span class="b-fill" style="width:${(v / m) * 100}%"></span></span>
          <span class="b-val">${v}</span>
        </div>`
      )
      .join("");
  };
  renderBars(d.by_specialty, "#by-specialty");
  const st = {};
  for (const [k, v] of Object.entries(d.by_status)) st[STATUS_LABELS[k] || k] = v;
  renderBars(st, "#by-status");
}

/* ---------------- tabs & wiring ---------------- */
function switchTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $("#view-routes").classList.toggle("active", name === "routes");
  $("#view-dashboard").classList.toggle("active", name === "dashboard");
  if (name === "dashboard") loadDashboard();
}

let searchTimer;
$("#search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadRoutes, 250);
});
$("#filter-specialty").addEventListener("change", loadRoutes);
$("#filter-priority").addEventListener("change", loadRoutes);
$$(".tab").forEach((t) => (t.onclick = () => switchTab(t.dataset.tab)));
$$("[data-advance]").forEach((b) => (b.onclick = () => advance(Number(b.dataset.advance))));

(async function init() {
  await loadMeta();
  await loadRoutes();
  const d = await api("/api/dashboard");
  $("#clock").textContent = fmtDate(d.now);
  if (LIST.length) selectRoute(LIST[0].id);
})();
