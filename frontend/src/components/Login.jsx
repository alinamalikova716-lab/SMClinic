import { useState } from "react";

export const ROLES = {
  chief: "Главный врач",
  coordinator: "Координатор",
  doctor: "Профильный врач",
  surgeon: "Хирург",
  oncologist: "Онколог",
};

// Экран входа в личный кабинет: выбирается роль (и специальность для врача).
// Дальше сервер отдаёт только те протоколы, которые человеку положено видеть.
export default function Login({ specialties, onLogin }) {
  const [role, setRole] = useState("coordinator");
  const [specialty, setSpecialty] = useState(specialties[0] || "");
  const [name, setName] = useState("");

  const submit = (e) => {
    e.preventDefault();
    onLogin({ role, specialty: role === "doctor" ? specialty : "", name: name.trim() });
  };

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand">
          <img src="/logo.svg" alt="" className="brand-logo" />
          <div>
            <div className="brand-title">СМ-Клиника</div>
            <div className="brand-sub">личный кабинет</div>
          </div>
        </div>

        <label className="login-label">Роль</label>
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          {Object.entries(ROLES).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>

        {role === "doctor" && (
          <>
            <label className="login-label">Специальность</label>
            <select value={specialty} onChange={(e) => setSpecialty(e.target.value)}>
              {specialties.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </>
        )}

        <label className="login-label">Имя (необязательно)</label>
        <input
          type="text"
          value={name}
          placeholder="Иван Иванович"
          onChange={(e) => setName(e.target.value)}
        />

        <button className="btn primary login-btn" type="submit">Войти в кабинет</button>
        <div className="login-hint">
          Главный врач и координатор видят все протоколы. Остальные специалисты —
          только пациентов, направленных по своему профилю.
        </div>
      </form>
    </div>
  );
}
