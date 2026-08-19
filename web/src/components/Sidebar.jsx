const items = [
  "CORE",
  "TASKS",
  "AGENTS",
  "MONEY",
  "ORDERS",
  "SOCIAL",
  "CALENDAR",
  "MEMORY",
  "ACTIVITY",
  "SETTINGS"
];

export default function Sidebar({ active, setActive }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <strong>MR AI</strong>
        <span>CHIEF OF STAFF</span>
      </div>

      <nav>
        {items.map(item => (
          <button
            key={item}
            className={active === item ? "active" : ""}
            onClick={() => setActive(item)}
          >
            <span className="nav-dot" />
            {item}
          </button>
        ))}
      </nav>
    </aside>
  );
}
