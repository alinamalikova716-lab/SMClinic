import { splitProtocol } from "../lib/util.js";

// Единое окно просмотра полного протокола (используется в карточке маршрута
// и в разделе «Требует уточнения»).
export default function ProtocolModal({ title, text, onClose }) {
  if (!text) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal protocol-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Протокол исследования</h2>
          <button className="modal-x" onClick={onClose}>×</button>
        </div>
        {title && <div className="protocol-sub">Находка: {title}</div>}
        <div className="protocol-body">
          {splitProtocol(text).map((b, i) =>
            b.header ? (
              <div className="pb-head" key={i}>{b.text}</div>
            ) : (
              <p key={i}>{b.text}</p>
            )
          )}
        </div>
      </div>
    </div>
  );
}
