import Core from "./Core";
import Chat from "./Chat";
import DashboardWorldMap from "./DashboardWorldMap";

function safePercent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : null;
}

function formatUptime(seconds) {
  const number = Number(seconds);
  if (!Number.isFinite(number)) return "N/A";
  const days = Math.floor(number / 86400);
  const hours = Math.floor((number % 86400) / 3600);
  const minutes = Math.floor((number % 3600) / 60);
  return `${days}d ${String(hours).padStart(2, "0")}h ${String(minutes).padStart(2, "0")}m`;
}

function formatTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function MetricBar({ label, value }) {
  const percent = safePercent(value);
  return (
    <div className="hud-metric">
      <div className="hud-metric-head">
        <span>{label}</span>
        <strong>{percent === null ? "N/A" : `${percent}%`}</strong>
      </div>
      <div className="hud-track">
        <span style={percent === null ? undefined : { width: `${percent}%` }} />
      </div>
    </div>
  );
}

function Panel({ eyebrow, title, badge, children, className = "", action }) {
  return (
    <section className={`hud-panel ${className}`}>
      <div className="hud-panel-head">
        <div>
          {eyebrow && <span className="hud-eyebrow">{eyebrow}</span>}
          <h2>{title}</h2>
        </div>
        <div className="hud-panel-actions">
          {action}
          {badge && <span className="hud-badge">{badge}</span>}
        </div>
      </div>
      {children}
    </section>
  );
}

function CurrentProfile({ telemetry }) {
  const metrics = [
    ["CPU", telemetry?.cpu_percent],
    ["MEMORY", telemetry?.memory_percent],
    ["NETWORK", null],
    ["STORAGE", telemetry?.storage_percent],
    ["GPU", telemetry?.gpu?.utilization_percent],
  ];

  return (
    <div className="profile-card">
      {metrics.map(([label, value]) => (
        <MetricBar key={label} label={label} value={value} />
      ))}
      <div className="profile-note">
        NETWORK bytes: {Number.isFinite(Number(telemetry?.network?.bytes_sent)) ? telemetry.network.bytes_sent.toLocaleString() : "N/A"} sent ·{" "}
        {Number.isFinite(Number(telemetry?.network?.bytes_received)) ? telemetry.network.bytes_received.toLocaleString() : "N/A"} received
      </div>
    </div>
  );
}

function MissionOverview({ tasks = [] }) {
  const active = tasks.filter(task => !["COMPLETED", "FAILED"].includes(String(task.status || "").toUpperCase()));
  const completed = tasks.filter(task => String(task.status || "").toUpperCase() === "COMPLETED").length;
  const latest = active[0] || tasks[0];

  return (
    <div className="mission-overview">
      <div className="mission-copy">
        <p>Execute, coordinate and verify assigned operations with evidence from the real MR AI runtime.</p>
        <span>CURRENT FOCUS</span>
        <strong>{latest?.title || "No active mission"}</strong>
      </div>
      <div className="mission-chart" aria-label="Current task progress profile">
        {active.slice(0, 7).map(task => {
          const progress = safePercent(task.progress);
          return (
            <div className="mission-chart-row" key={task.id}>
              <small>{String(task.title || "Task").slice(0, 22)}</small>
              <div className="hud-track">
                <span style={progress === null ? undefined : { width: `${progress}%` }} />
              </div>
              <b>{progress === null ? "N/A" : `${progress}%`}</b>
            </div>
          );
        })}
        {active.length === 0 && <div className="hud-empty">NO ACTIVE OPERATIONS</div>}
      </div>
      <div className="mission-stats">
        <div><span>ACTIVE</span><strong>{active.length}</strong></div>
        <div><span>COMPLETED</span><strong>{completed}</strong></div>
        <div><span>TOTAL</span><strong>{tasks.length}</strong></div>
      </div>
    </div>
  );
}

const capabilityItems = [
  ["◉", "AI CHAT", "MR AI Core"],
  ["⌁", "TELEMETRY", "Local system"],
  ["↗", "BROWSER", "Browser Hands"],
  ["⌖", "DEVICES", "Device Bridge"],
  ["◎", "RESEARCH", "Web intelligence"],
  ["◇", "MEMORY", "User memory"],
  ["✉", "GMAIL", "OAuth mail"],
];

function Capabilities({ services = {}, gmailStatus = null }) {
  const extension = services.extension || "NOT_CONNECTED";
  return (
    <div className="capability-grid">
      {capabilityItems.map(([icon, label, source]) => {
        const status =
          label === "BROWSER"
            ? extension
            : label === "RESEARCH"
              ? "AVAILABLE"
              : label === "DEVICES"
                ? "LOCAL SENSOR"
                : label === "MEMORY"
                  ? services.memory || "ONLINE"
                  : "ONLINE";

        return (
          <div className="capability-item" key={label}>
            <div className="capability-icon">{icon}</div>
            <strong>{label}</strong>
            <small>{source}</small>
            <span>{status}</span>
          </div>
        );
      })}
    </div>
  );
}

function ActivityList({ activities = [] }) {
  return (
    <div className="hud-list">
      {activities.slice(0, 5).map(item => (
        <div className="hud-list-row" key={item.id}>
          <span className="list-icon">◈</span>
          <div>
            <strong>{item.action || "ACTIVITY"}</strong>
            <small>{item.details || "Verified runtime event"}</small>
          </div>
          <time>{formatTime(item.created_at || item.timestamp)}</time>
        </div>
      ))}
      {activities.length === 0 && <div className="hud-empty">NO VERIFIED ACTIVITY YET</div>}
    </div>
  );
}

function TargetRadar({ findings = [] }) {
  const visible = findings.slice(0, 8);
  return (
    <div className="target-radar-wrap">
      <div className="target-radar">
        <div className="target-radar-ring ring-a" />
        <div className="target-radar-ring ring-b" />
        <div className="target-radar-ring ring-c" />
        <div className="target-radar-cross cross-v" />
        <div className="target-radar-cross cross-h" />
        <div className="target-radar-sweep" />
        <div className="target-radar-core">MR</div>
        {visible.map((finding, index) => {
          const angle = (index / Math.max(1, visible.length)) * Math.PI * 2;
          const radius = 28 + (index % 3) * 10;
          return (
            <span
              className="target-radar-dot"
              key={finding.id || finding.address || finding.label || index}
              style={{
                left: `${50 + Math.cos(angle) * radius}%`,
                top: `${50 + Math.sin(angle) * radius}%`,
              }}
              title={finding.label || finding.address || finding.type || "Sensor finding"}
            />
          );
        })}
      </div>
      <div className="target-meta">
        <div><span>TARGET</span><strong>{findings.length ? "ONLINE" : "NO SENSOR CONTACT"}</strong></div>
        <div><span>COORDINATES</span><strong>GPS NOT ASSUMED</strong></div>
        <div><span>CONTACTS</span><strong>{findings.length}</strong></div>
        <div><span>DIRECTION</span><strong>UNKNOWN</strong></div>
      </div>
    </div>
  );
}

function ActiveTasks({ tasks = [] }) {
  const visible = tasks.slice(0, 5);
  return (
    <div className="task-list">
      {visible.map((task, index) => {
        const progress = safePercent(task.progress);
        const status = String(task.status || "PENDING").toUpperCase();
        return (
          <div className="task-row" key={task.id}>
            <span className="task-number">{String(index + 1).padStart(2, "0")}</span>
            <div className="task-main">
              <strong>{task.title || "Untitled task"}</strong>
              <div className="hud-track"><span style={progress === null ? undefined : { width: `${progress}%` }} /></div>
            </div>
            <span className={`task-status status-${status.toLowerCase()}`}>{status}</span>
            <b>{progress === null ? "N/A" : `${progress}%`}</b>
          </div>
        );
      })}
      {visible.length === 0 && <div className="hud-empty">NO TASKS RECORDED</div>}
    </div>
  );
}

function MemoryBank({ memories = [] }) {
  const latest = memories[0];
  return (
    <div className="memory-bank">
      <div className="memory-visual">◇</div>
      <div className="memory-data">
        <div><span>TOTAL MEMORIES</span><strong>{memories.length.toLocaleString()}</strong></div>
        <div><span>RECENT RECORDS</span><strong>{Math.min(memories.length, 10)}</strong></div>
        <div><span>LAST KEY</span><strong>{latest?.key || "N/A"}</strong></div>
        <div><span>STATE</span><strong>{memories.length ? "STORED" : "EMPTY"}</strong></div>
      </div>
    </div>
  );
}

function Architecture() {
  return (
    <div className="architecture">
      <div className="architecture-side left">
        <span>SENSOR INPUT</span>
        <span>DATA PROCESSING</span>
        <span>ML ENGINE</span>
      </div>
      <div className="architecture-core">MR AI<br /><small>CORE</small></div>
      <div className="architecture-side right">
        <span>DECISION ENGINE</span>
        <span>ACTION MODULE</span>
        <span>FEEDBACK LOOP</span>
      </div>
    </div>
  );
}

function Communication({ services = {}, gmailStatus = null }) {
  const rows = [
    ["SESSION", "AUTHENTICATED"],
    ["BACKEND", services.ai_core || "N/A"],
    ["DATABASE", services.database || "N/A"],
    ["GEMINI", services.gemini || "N/A"],
    ["BROWSER", services.extension || "N/A"],
    ["GMAIL", gmailStatus?.status || "N/A"],
  ];
  return (
    <div className="communication">
      <div className="communication-globe">◎</div>
      <div className="communication-list">
        {rows.map(([label, value]) => (
          <div key={label}><span>{label}</span><strong>{value}</strong></div>
        ))}
      </div>
    </div>
  );
}

export default function DashboardHome({
  system,
  agents = [],
  radarFindings = [],
  tasks = [],
  memories = [],
  activities = [],
  gmailStatus = null,
  coreState = "IDLE",
  working = false,
  onRefresh,
  onState,
  onModToggle,
  onPowerCommand,
}) {
  const telemetry = system?.telemetry || {};
  const services = system?.services || {};

  return (
    <div className="command-dashboard">
      <div className="dashboard-brandline">
        <div>
          <span className="hud-eyebrow">MOG343 // MR AI STAN</span>
          <h2>JARVIS AI</h2>
          <p>DIGITAL CHIEF OF STAFF</p>
        </div>
        <div className="dashboard-state">
          <span>{working ? "WORKING MODE" : "NORMAL MODE"}</span>
          <b>{system?.services?.ai_core === "ONLINE" && system?.services?.database === "ONLINE" ? "CORE OPERATIONAL" : "CHECK SYSTEM STATE"}</b>
        </div>
      </div>

      <div className="dashboard-grid grid-top">
        <Panel eyebrow="SYSTEM STATUS" title="System Status" action={<button className="hud-mini-button" onClick={onRefresh}>REFRESH</button>}>
          <CurrentProfile telemetry={telemetry} />
        </Panel>

        <Panel eyebrow="AI CORE STATUS" title="AI Core Status" badge={coreState}>
          <div className="core-status-layout">
            <div className="core-status-copy">
              <div><span>AI MODEL</span><strong>{system?.ai?.model || "N/A"}</strong></div>
              <div><span>AI TIER</span><strong>{system?.ai?.tier || "N/A"}</strong></div>
              <div><span>UPTIME</span><strong>{formatUptime(telemetry.uptime_seconds)}</strong></div>
              <div><span>STATUS</span><strong>{services.ai_core || "N/A"}</strong></div>
              <div><span>RESPONSE TIME</span><strong>N/A</strong></div>
              <div><span>LEARNING RATE</span><strong>N/A</strong></div>
            </div>
            <Core state={coreState} modActive={working} />
          </div>
        </Panel>

        <Panel eyebrow="MISSION OVERVIEW" title="Mission Overview">
          <MissionOverview tasks={tasks} />
        </Panel>
      </div>

      <div className="dashboard-grid grid-middle">
        <Panel eyebrow="CURRENT SYSTEM PROFILE" title="Live Metrics">
          <div className="metric-profile-chart">
            {[
              ["CPU", telemetry.cpu_percent],
              ["RAM", telemetry.memory_percent],
              ["DISK", telemetry.storage_percent],
              ["GPU", telemetry.gpu?.utilization_percent],
            ].map(([label, value]) => {
              const percent = safePercent(value);
              return (
                <div className="profile-bar" key={label}>
                  <span>{label}</span>
                  <div className="hud-track"><i style={percent === null ? undefined : { height: `${Math.max(8, percent)}%` }} /></div>
                  <b>{percent === null ? "N/A" : `${percent}%`}</b>
                </div>
              );
            })}
          </div>
          <div className="profile-caption">
            <span>REAL LOCAL TELEMETRY</span>
            <strong>NO FABRICATED HISTORY</strong>
          </div>
        </Panel>

        <Panel eyebrow="AI CORE" title="MR AI Presence" className="core-dashboard-panel">
          <div className="core-dashboard-stage">
            <Core state={coreState} modActive={working} />
          </div>
        </Panel>

        <Panel eyebrow="CAPABILITIES" title="Platform Capabilities">
          <Capabilities services={services} gmailStatus={gmailStatus} />
        </Panel>
      </div>

      <div className="dashboard-grid grid-lower">
        <Panel eyebrow="ACTIVE TASKS" title="Active Tasks" badge={`${tasks.length} TOTAL`}>
          <ActiveTasks tasks={tasks} />
        </Panel>

        <Panel eyebrow="VOICE INTERACTION" title="MR AI Chat" className="dashboard-chat-panel">
          <div className="voice-preview">
            <div className="voice-wave-line"><span /><span /><span /><span /><span /><span /><span /></div>
            <p>Command channel is connected to the shared AI core. Voice and text requests use the same operational routing.</p>
          </div>
          <Chat onState={onState} onModToggle={onModToggle} onPowerCommand={onPowerCommand} />
        </Panel>

        <Panel eyebrow="TARGET ACQUISITION" title="Target Radar" badge={`${radarFindings.length} CONTACTS`}>
          <TargetRadar findings={radarFindings} />
        </Panel>
      </div>

      <div className="dashboard-grid grid-map">
        <Panel eyebrow="WORLD MAP" title="Authorized World Map">
          <DashboardWorldMap />
        </Panel>
      </div>

      <div className="dashboard-grid grid-bottom">
        <Panel eyebrow="MEMORY BANK" title="Memory Bank">
          <MemoryBank memories={memories} />
          <button className="hud-wide-button">OPEN MEMORY</button>
        </Panel>

        <Panel eyebrow="SYSTEM ARCHITECTURE" title="System Architecture">
          <Architecture />
        </Panel>

        <Panel eyebrow="RECENT ACTIVITIES" title="Recent Activities">
          <ActivityList activities={activities} />
        </Panel>

        <Panel eyebrow="COMMUNICATIONS" title="Communications">
          <Communication services={services} gmailStatus={gmailStatus} />
        </Panel>
      </div>

      <div className="dashboard-footerline">
        <span>OWNER // BOSS FERISI</span>
        <span>MANAGER // MR AI</span>
        <span>WORKSPACE // MOG343</span>
        <span>CREW // {agents.length} REGISTERED AGENTS</span>
      </div>
    </div>
  );
}
