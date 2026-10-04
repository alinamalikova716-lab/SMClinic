// Тонкий слой доступа к локальному API.
// Vite проксирует /api на FastAPI (127.0.0.1:8000), см. vite.config.js
async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

const json = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const getMeta = () => api("/api/meta");
export const getRoutes = (params) => api(`/api/routes?${params.toString()}`);
export const getRoute = (id) => api(`/api/routes/${id}`);
export const sendAction = (id, action) => api(`/api/routes/${id}/action`, json({ action }));
export const advanceTime = (hours) => api("/api/simulate/advance", json({ hours }));
export const getDashboard = () => api("/api/dashboard");

// Приём протокола: Word/.txt -> находки + маршрут (полный цикл)
export const analyzeFile = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return api("/api/analyze-file", { method: "POST", body: fd });
};
export const analyzeText = (text, studyType = "") =>
  api("/api/analyze", json({ text, study_type: studyType }));

// Очередь «Требует уточнения»
export const getReviews = () => api("/api/reviews");
export const resolveReview = (id, decision) =>
  api(`/api/reviews/${id}/resolve`, json({ decision }));

// Протоколы без значимых находок
export const getNormals = () => api("/api/normals");
