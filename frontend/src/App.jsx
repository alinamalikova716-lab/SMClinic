import { useCallback, useEffect, useRef, useState } from "react";
import { advanceTime, getDashboard, getMeta, getNormals, getReviews, getRoute, getRoutes, resolveReview, sendAction } from "./api.js";
import { fmtDate, pLabel as makePLabel } from "./lib/util.js";
import Queue from "./components/Queue.jsx";
import RouteDetail from "./components/RouteDetail.jsx";
import Dashboard from "./components/Dashboard.jsx";
import UploadProtocol from "./components/UploadProtocol.jsx";
import Reviews from "./components/Reviews.jsx";
import Normals from "./components/Normals.jsx";

export default function App() {
  const [meta, setMeta] = useState(null);
  const [routes, setRoutes] = useState([]);
  const [current, setCurrent] = useState(null);
  const [now, setNow] = useState(null);
  const [tab, setTab] = useState("routes");
  const [dashboard, setDashboard] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [normals, setNormals] = useState([]);
  const [toast, setToast] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);

  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState("");
  const [specialty, setSpecialty] = useState("");

  const firstLoad = useRef(true);
  const toastTimer = useRef(null);

  const pLabel = makePLabel(meta);
  const actionLabel = (a) => meta?.action_labels?.[a] || a;

  const showToast = useCallback((msg) => {
    setToast(msg);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 2600);
  }, []);

  const loadRoutes = useCallback(async (autoSelect = false) => {
    const params = new URLSearchParams();
    if (search.trim()) params.set("q", search.trim());
    if (priority) params.set("priority", priority);
    if (specialty) params.set("specialty", specialty);
    const data = await getRoutes(params);
    setRoutes(data.routes);
    setNow(data.now);
    if (autoSelect && data.routes.length) select(data.routes[0].id);
  }, [search, priority, specialty]);

  const select = useCallback(async (id) => {
    const r = await getRoute(id);
    setCurrent(r);
  }, []);

  const doAction = useCallback(
    async (action) => {
      if (!current) return;
      const updated = await sendAction(current.id, action);
      setCurrent(updated);
      showToast(actionLabel(action));
      await loadRoutes();
    },
    [current, loadRoutes, showToast, meta]
  );

  const advance = useCallback(
    async (hours) => {
      const data = await advanceTime(hours);
      setNow(data.now);
      showToast(
        data.events.length
          ? `Прошло ${hours} ч · событий: ${data.events.length}`
          : `Прошло ${hours} ч · новых событий нет`
      );
      await loadRoutes();
      if (current) await select(current.id);
      if (tab === "dashboard") setDashboard(await getDashboard());
    },
    [current, loadRoutes, select, showToast, tab]
  );

  const loadReviews = useCallback(async () => setReviews((await getReviews()).reviews), []);
  const loadNormals = useCallback(async () => setNormals((await getNormals()).normals), []);
  const refreshAux = useCallback(async () => {
    await Promise.all([loadReviews(), loadNormals()]);
  }, [loadReviews, loadNormals]);

  const switchTab = useCallback(
    async (name) => {
      setTab(name);
      if (name === "dashboard") setDashboard(await getDashboard());
      if (name === "reviews") await loadReviews();
      if (name === "normals") await loadNormals();
    },
    [loadReviews, loadNormals]
  );

  const onResolve = useCallback(
    async (id, decision) => {
      await resolveReview(id, decision);
      showToast(decision === "confirm" ? "Находка подтверждена, маршрут создан" : "Находка отклонена");
      await loadReviews();
      await loadRoutes();
    },
    [loadReviews, loadRoutes, showToast]
  );

  // протокол обработан: закрыть окно, обновить список, открыть созданный маршрут
  const openCreated = useCallback(
    async (id) => {
      setUploadOpen(false);
      await refreshAux();
      if (id) {
        setTab("routes");
        await loadRoutes();
        await select(id);
        showToast("Создан маршрут");
      } else {
        showToast("Протокол обработан и сохранён");
      }
    },
    [loadRoutes, select, showToast, refreshAux]
  );

  // первичная загрузка
  useEffect(() => {
    (async () => {
      setMeta(await getMeta());
      await loadReviews();
      await loadRoutes(true);
      firstLoad.current = false;
    })();
  }, []);

  // перезагрузка списка при смене фильтров (поиск — с задержкой)
  useEffect(() => {
    if (firstLoad.current) return;
    const t = setTimeout(() => loadRoutes(), 250);
    return () => clearTimeout(t);
  }, [search, priority, specialty]);

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <img className="brand-logo" src="/logo.svg" alt="" />
          <div className="brand-title">СМ-Клиника</div>
        </div>
        <nav className="tabs">
          <button className={"tab" + (tab === "routes" ? " active" : "")} onClick={() => switchTab("routes")}>
            Маршруты
          </button>
          <button className={"tab" + (tab === "reviews" ? " active" : "")} onClick={() => switchTab("reviews")}>
            Требует уточнения
            {reviews.length > 0 && <span className="tab-badge">{reviews.length}</span>}
          </button>
          <button className={"tab" + (tab === "normals" ? " active" : "")} onClick={() => switchTab("normals")}>
            Без патологий
          </button>
          <button className={"tab" + (tab === "dashboard" ? " active" : "")} onClick={() => switchTab("dashboard")}>
            Статистика
          </button>
        </nav>
        <button className="btn-upload" onClick={() => setUploadOpen(true)}>
          + Загрузить протокол
        </button>
        <div className="clock">
          <span className="clock-label">Местное время</span>
          <span className="clock-value">{fmtDate(now)}</span>
        </div>
      </header>

      <main>
        <section className={"view" + (tab === "routes" ? " active" : "")}>
          <Queue
            routes={routes}
            currentId={current?.id}
            onSelect={select}
            search={search}
            setSearch={setSearch}
            priority={priority}
            setPriority={setPriority}
            specialty={specialty}
            setSpecialty={setSpecialty}
            specialties={meta?.specialties || []}
            pLabel={pLabel}
            now={now}
          />
          <RouteDetail route={current} meta={meta} now={now} onAction={doAction} pLabel={pLabel} />
        </section>

        <section className={"view view-page" + (tab === "reviews" ? " active" : "")}>
          <Reviews reviews={reviews} onResolve={onResolve} pLabel={pLabel} />
        </section>

        <section className={"view view-page" + (tab === "normals" ? " active" : "")}>
          <Normals normals={normals} />
        </section>

        <section className={"view view-page" + (tab === "dashboard" ? " active" : "")}>
          <Dashboard data={dashboard} />
        </section>
      </main>

      <UploadProtocol
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onCreated={openCreated}
        onProcessed={async () => {
          await loadRoutes();
          await refreshAux();
        }}
      />

      <div className={"toast" + (toast ? " show" : "")}>{toast}</div>
    </>
  );
}
