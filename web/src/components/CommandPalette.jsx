import { useEffect, useState } from "react";

export default function CommandPalette({ open, onClose, onNavigate, onToggleMode }) {
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!open) return;
    setQuery("");
    const onKeyDown = event => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const actions = [
    ["dashboard", "Open Dashboard"],
    ["core", "Open AI Core"],
    ["agents", "Open Agents"],
    ["browser", "Open Browser Hands"],
    ["device", "Open Device Lab"],
    ["creative", "Open Creative Studio"],
    ["map", "Open Tracking Map"],
    ["security", "Open Google Protection"],
    ["tools", "Open Toolbox"],
    ["tasks", "Open Tasks"],
    ["memory", "Open Memory"],
    ["system", "Open System"],
  ];

  const filtered = actions.filter(([, label]) =>
    label.toLowerCase().includes(query.trim().toLowerCase())
  );

  function choose(action) {
    onNavigate(action);
    onClose();
  }

  return (
    <div className="palette-backdrop" onMouseDown={onClose}>
      <div className="command-palette" onMouseDown={event => event.stopPropagation()}>
        <div className="palette-top">
          <span className="eyebrow">COMMAND PALETTE</span>
          <button className="ghost-button palette-close" onClick={onClose}>ESC</button>
        </div>
        <input
          autoFocus
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Type a destination or action..."
        />
        <div className="palette-actions">
          <button className="palette-action mode-action" onClick={() => { onToggleMode(); onClose(); }}>
            <strong>Toggle Working Mode</strong>
            <span>Switch NORMAL / WORKING</span>
          </button>
          {filtered.map(([id, label]) => (
            <button className="palette-action" onClick={() => choose(id)} key={id}>
              <strong>{label}</strong>
              <span>{id.toUpperCase()}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
