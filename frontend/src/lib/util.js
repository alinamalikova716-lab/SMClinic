export const STATUS_LABELS = {
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

export const PRIORITY_RU = {
  emergency: "Экстренно",
  urgent: "Срочно",
  planned: "Планово",
  watch: "Наблюдение",
};

export const pLabel = (meta) => (p) =>
  meta?.priorities?.[p]?.label || PRIORITY_RU[p] || p;

export const fmtDate = (iso) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

export const isOverdue = (route, now) =>
  !!now &&
  !!route.due_at &&
  new Date(route.due_at) < new Date(now) &&
  !["closed", "not_engaged"].includes(route.status);

// Приводит «сырой» текст протокола к читаемому виду:
// убирает пустые строки, склеивает «Дата приема:» + «11.09.2026» в одну строку,
// выделяет заголовки разделов. Не склеивает всё в один огромный абзац.
export function splitProtocol(text) {
  if (!text) return [];
  const raw = text
    .replace(/\r/g, "")
    .replace(/\u00a0/g, " ")
    .split("\n")
    .map((s) => s.trim());

  const lines = [];
  for (let i = 0; i < raw.length; i++) {
    const cur = raw[i];
    if (!cur) continue;
    const next = (raw[i + 1] || "").trim();
    // метка «Дата приема:» + короткое значение -> в одну строку
    if (cur.endsWith(":") && next && next.length <= 45 && !next.endsWith(":")) {
      lines.push(cur + " " + next);
      i++;
      continue;
    }
    lines.push(cur);
  }

  const isHeader = (s) =>
    s.length <= 60 && !s.endsWith(":") && s === s.toUpperCase() && /[А-ЯЁA-Z]/.test(s);

  return lines.map((s) => ({ text: s, header: isHeader(s) }));
}
