// Предпросмотр того, что увидит пациент: нейтральный текст, БЕЗ диагноза.
export default function PushPreview({ text }) {
  return (
    <div className="panel">
      <h3>
        Глазами пациента
      </h3>
      <div className="patient-preview">
        <div className="pp-head">
          <span className="pp-dot" />
          <span className="pp-title">Push · Личный кабинет</span>
          <span className="pp-note">отправлено автоматически</span>
        </div>
        <div className="pp-card">
          <div className="pp-app">СМ-Клиника · сейчас</div>
          <div className="pp-msg">{text}</div>
          <div className="pp-buttons">
            <button className="pp-btn">Записаться к специалисту</button>
            <button className="pp-btn ghost">Онлайн-консультация</button>
            <button className="pp-btn ghost">Оставить заявку на звонок</button>
          </div>
        </div>
        <div className="pp-hide">
          В сообщении намеренно нет диагноза, названия болезни и результатов — только нейтральная
          рекомендация и безопасный следующий шаг.
        </div>
      </div>
    </div>
  );
}
