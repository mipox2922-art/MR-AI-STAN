import { useEffect, useState } from "react";
import { getActivity } from "../api";

export default function Activity() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    getActivity()
      .then(setItems)
      .catch(() => {});
  }, []);

  return (
    <section className="activity-panel">
      <div className="panel-title">
        VERIFIED ACTIVITY
      </div>

      {items.length === 0 ? (
        <div className="empty">
          Hakuna activity bado.
        </div>
      ) : (
        items.map(item => (
          <div className="activity-row" key={item.id}>
            <strong>{item.action}</strong>
            <span>{item.details || ""}</span>
          </div>
        ))
      )}
    </section>
  );
}
