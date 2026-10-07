import { useMemo, useState } from "react";
import { dispatchTool } from "../api";
import Core from "./Core";
import Chat from "./Chat";

function pct(value) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : null;
}

function formatUptime(seconds) {
  const n = Number(seconds);
  if (!Number.isFinite(n)) return "N/A";
  const d = Math.floor(n / 86400);
  const h = Math.floor((n % 86400) / 3600);
  const m = Math.floor((n % 3600) / 60);
  return `${d}d ${String(h).padStart(2, "0")}h ${String(m).padStart(2, "0")}m`;
}

function formatTime(value) {
  if (!value) return "--";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function Panel({ eyebrow, title, badge, children, className = "", action }) {
  return (
    <section className={`cc-panel ${className}`}>
      <header className="cc-panel-head">
        <div>
          <span className="cc-eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
        </div>
        <div className="cc-panel-actions">
          {action}
          {badge && <span className="cc-badge">{badge}</span>}
        </div>
      </header>
      {children}
    </section>
  );
}

function Metric({ label, value }) {
  const valuePct = pct(value);
  return (
    <div className="cc-metric">
      <div className="cc-metric-top">
        <span>{label}</span>
        <strong>{valuePct === null ? "N/A" : `${valuePct}%`}</strong>
      </div>
      <div className="cc-meter">
        <i style={valuePct === null ? undefined : { width: `${valuePct}%` }} />
      </div>
    </div>
  );
}

function formatBytes(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "N/A";
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(2)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${Math.round(n)} B`;
}

function formatRate(bytesPerSecond) {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond < 0) return "WAITING";
  return `${formatBytes(bytesPerSecond)}/s`;
}

function NetworkMetric({ telemetry, telemetryHistory = [] }) {
  const currentSent = Number(telemetry?.network?.bytes_sent);
  const currentReceived = Number(telemetry?.network?.bytes_received);
  const previous = telemetryHistory.length > 1 ? telemetryHistory[telemetryHistory.length - 2] : null;
  const elapsedSeconds = previous?.captured_at
    ? Math.max(0.1, (Date.now() - Number(previous.captured_at)) / 1000)
    : null;

  const txRate = previous && elapsedSeconds && Number.isFinite(currentSent) && Number.isFinite(Number(previous.network?.bytes_sent))
    ? Math.max(0, currentSent - Number(previous.network.bytes_sent)) / elapsedSeconds
    : null;
  const rxRate = previous && elapsedSeconds && Number.isFinite(currentReceived) && Number.isFinite(Number(previous.network?.bytes_received))
    ? Math.max(0, currentReceived - Number(previous.network.bytes_received)) / elapsedSeconds
    : null;

  return (
    <div className="cc-metric cc-network-metric">
      <div className="cc-metric-top">
        <span>NETWORK</span>
        <strong>{txRate === null && rxRate === null ? "WAITING" : "LIVE"}</strong>
      </div>
      <div className="cc-network-rates">
        <span>TX {formatRate(txRate)}</span>
        <span>RX {formatRate(rxRate)}</span>
      </div>
    </div>
  );
}

function SystemStatus({ telemetry, telemetryHistory, connectionState, lastRefreshAt, onRefresh }) {
  const refreshLabel = lastRefreshAt ? new Date(lastRefreshAt).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "WAITING";
  return (
    <div className="cc-system-status">
      <Metric label="CPU USAGE" value={telemetry?.cpu_percent} />
      <Metric label="MEMORY" value={telemetry?.memory_percent} />
      <NetworkMetric telemetry={telemetry} telemetryHistory={telemetryHistory} />
      <Metric label="STORAGE" value={telemetry?.storage_percent} />
      <Metric label="GPU" value={telemetry?.gpu?.utilization_percent} />
      <div className="cc-system-footer">
        <span>RUNTIME · {connectionState || "CONNECTING"} · {refreshLabel}</span>
        <strong>
          TX {Number.isFinite(Number(telemetry?.network?.bytes_sent)) ? formatBytes(telemetry.network.bytes_sent) : "N/A"}
          {" · "}
          RX {Number.isFinite(Number(telemetry?.network?.bytes_received)) ? formatBytes(telemetry.network.bytes_received) : "N/A"}
        </strong>
      </div>
      <button className="cc-inline-button" onClick={onRefresh}>REFRESH TELEMETRY</button>
    </div>
  );
}

function MissionOverview({ tasks = [] }) {
  const active = tasks.filter(t => !["COMPLETED", "FAILED"].includes(String(t.status || "").toUpperCase()));
  const completed = tasks.filter(t => String(t.status || "").toUpperCase() === "COMPLETED").length;
  const values = active.slice(0, 8).map(t => pct(t.progress)).filter(v => v !== null);
  const chart = values.length
    ? values.map((v, i) => {
        const x = values.length === 1 ? 8 : 8 + (i / (values.length - 1)) * 84;
        const y = 45 - v * 0.36;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ")
    : "";
  const focus = active[0]?.title || tasks[0]?.title || "NO ACTIVE MISSION";

  return (
    <div className="cc-mission">
      <div className="cc-mission-copy">
        <p>Execute, monitor and verify assigned operations with evidence from the MR AI runtime.</p>
        <span>CURRENT FOCUS</span>
        <strong>{focus}</strong>
      </div>
      <div className="cc-mission-graph">
        <div className="cc-graph-grid" />
        <svg viewBox="0 0 100 50" preserveAspectRatio="none" aria-label="Task progress history">
          {chart && <polyline points={chart} fill="none" stroke="var(--accent)" strokeWidth="1.2" />}
          {values.map((v, i) => {
            const x = values.length === 1 ? 8 : 8 + (i / (values.length - 1)) * 84;
            const y = 45 - v * 0.36;
            return <circle key={i} cx={x} cy={y} r="1.35" fill="var(--accent)" />;
          })}
        </svg>
        {!chart && <span className="cc-chart-empty">WAITING FOR TASK DATA</span>}
        <div className="cc-chart-axis"><span>00</span><span>04</span><span>08</span><span>12</span><span>16</span><span>20</span><span>24</span></div>
      </div>
      <div className="cc-mission-stats">
        <div><span>ACTIVE</span><strong>{active.length}</strong></div>
        <div><span>DONE</span><strong>{completed}</strong></div>
        <div><span>TOTAL</span><strong>{tasks.length}</strong></div>
      </div>
    </div>
  );
}

function Radar({ findings = [] }) {
  const points = findings.slice(0, 12);
  const contactLabel = points.length ? `${points.length} CONTACTS` : "NO CONTACTS";
  return (
    <div className="cc-radar-wrap">
      <div className="cc-radar">
        <div className="cc-radar-grid" />
        <div className="cc-radar-sweep" />
        <div className="cc-radar-core">MR</div>
        {points.map((finding, index) => {
          const angle = (index / Math.max(1, points.length)) * Math.PI * 2 - Math.PI / 2;
          const radius = 28 + (index % 3) * 9;
          return (
            <span
              key={finding.id || finding.address || finding.label || index}
              className="cc-radar-dot"
              style={{ left: `${50 + Math.cos(angle) * radius}%`, top: `${50 + Math.sin(angle) * radius}%` }}
              title={finding.label || finding.address || finding.type || "Sensor contact"}
            />
          );
        })}
      </div>
      <div className="cc-radar-readout">
        <div><span>GLOBAL SCAN</span><strong>{findings.length ? "ACTIVE" : "STANDBY"}</strong></div>
        <div><span>CONTACTS</span><strong>{contactLabel}</strong></div>
        <div><span>SOURCE</span><strong>{findings.length ? "AUTHORIZED SENSORS" : "NO SENSOR DATA"}</strong></div>
      </div>
    </div>
  );
}

function HolographicWorldMap({ onOpenMap }) {
  const [position, setPosition] = useState(null);
  const [accuracy, setAccuracy] = useState(null);
  const [status, setStatus] = useState("READY");

  function locate() {
    if (!navigator.geolocation) {
      setStatus("NOT_SUPPORTED");
      return;
    }
    setStatus("REQUESTING...");
    navigator.geolocation.getCurrentPosition(
      current => {
        setPosition({ lat: current.coords.latitude, lon: current.coords.longitude });
        setAccuracy(current.coords.accuracy);
        setStatus("LOCATION VERIFIED");
      },
      error => {
        setStatus(error.code === error.PERMISSION_DENIED ? "PERMISSION DENIED" : "LOCATION ERROR");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
    );
  }

  const marker = position ? (
    <g className="cc-globe-marker" transform={`translate(${84 + (position.lon / 180) * 150} ${130 - (position.lat / 90) * 48})`}>
      <circle r="4" />
      <circle r="9" className="pulse-ring" />
    </g>
  ) : null;

  return (
    <div className="cc-world-map">
      <div className="cc-map-toolbar">
        <button className="cc-inline-button" onClick={locate}>LOCATE DEVICE</button>
        <button className="cc-inline-button" onClick={onOpenMap}>OPEN LIVE MAP</button>
        <span className="cc-map-state">{status}{accuracy != null ? ` · ±${Math.round(accuracy)}m` : ""}</span>
      </div>
      <div className="cc-globe-stage">
        <div className="cc-globe-halo" />
        <svg className="cc-globe-svg" viewBox="0 0 420 260" role="img" aria-label="MR AI holographic world map">
          <ellipse cx="210" cy="130" rx="156" ry="102" className="globe-shell" />
          <ellipse cx="210" cy="130" rx="156" ry="46" className="globe-line" />
          <ellipse cx="210" cy="130" rx="112" ry="102" className="globe-line" />
          <ellipse cx="210" cy="130" rx="58" ry="102" className="globe-line" />
          <ellipse cx="210" cy="130" rx="25" ry="102" className="globe-line" />
          <path d="M54 130 H366 M92 82 Q210 112 328 82 M92 178 Q210 148 328 178" className="globe-line" />
          <path d="M111 94 C95 81 83 70 77 54 C91 46 108 54 119 68 L137 80 L126 96 Z" className="land-shape" />
          <path d="M128 118 L151 111 L167 129 L158 151 L146 174 L139 154 L128 143 L122 128 Z" className="land-shape" />
          <path d="M179 72 L201 60 L222 67 L235 78 L225 92 L205 88 L190 99 L176 91 Z" className="land-shape" />
          <path d="M225 103 L248 96 L265 105 L284 106 L301 118 L291 130 L271 125 L258 136 L240 126 L228 134 L215 121 Z" className="land-shape" />
          <path d="M300 153 L320 146 L341 158 L337 174 L319 179 L304 168 Z" className="land-shape" />
          <path d="M196 145 L215 145 L223 162 L218 181 L205 194 L197 178 L184 170 L188 155 Z" className="land-shape" />
          {marker}
        </svg>
        <div className="cc-map-center-label"><span>MR AI</span><strong>LIVE WORLD VIEW</strong></div>
      </div>
      <div className="cc-map-readout">
        <div><span>STATUS</span><strong>{status}</strong></div>
        <div><span>LAT</span><strong>{position ? position.lat.toFixed(4) : "N/A"}</strong></div>
        <div><span>LON</span><strong>{position ? position.lon.toFixed(4) : "N/A"}</strong></div>
      </div>
    </div>
  );
}

function WebResearch() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("READY");
  const [results, setResults] = useState([]);

  async function runSearch(event) {
    event?.preventDefault();
    const value = query.trim();
    if (!value) return;

    setStatus("SEARCHING");
    try {
      const data = await dispatchTool(value);
      if (data?.route?.tool !== "searxng") {
        setResults([]);
        setStatus(String(data?.status || "NO_SEARCH_ROUTE").toUpperCase());
        return;
      }

      const searchResult = data.result || {};
      setResults(Array.isArray(searchResult.results) ? searchResult.results.slice(0, 4) : []);
      setStatus(String(searchResult.status || data.status || "COMPLETED").toUpperCase());
    } catch (error) {
      setResults([]);
      setStatus(error.message);
    }
  }

  return (
    <div className="cc-research">
      <form className="cc-research-search" onSubmit={runSearch}>
        <input
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="SEARCH THE WEB..."
          aria-label="Web research query"
        />
        <button type="submit" aria-label="Search">›</button>
      </form>
      <div className="cc-research-status">{status}</div>
      {results.length > 0 ? results.map((result, index) => (
        <article className="cc-research-item" key={result.url || index}>
          <span className="cc-research-icon">◎</span>
          <div>
            <a href={result.url} target="_blank" rel="noreferrer"><strong>{result.title || result.url}</strong></a>
            <small>{result.content || result.engine || "WEB SOURCE"}</small>
          </div>
        </article>
      )) : (
        <div className="cc-research-empty">
          {status === "READY" ? "ENTER A QUERY TO START VERIFIED WEB RESEARCH." : "NO VERIFIED RESULTS."}
        </div>
      )}
    </div>
  );
}

function QuickCommands() {
  const commands = [
    ["SCAN SYSTEM", "scan my system status"],
    ["ANALYZE DATA", "analyze my current system data"],
    ["WEB RESEARCH", "research the latest technology trends"],
    ["GENERATE REPORT", "generate a concise executive report of my current system"],
    ["SECURITY CHECK", "run a security status check"],
    ["OPTIMIZE", "identify safe optimization opportunities"],
  ];
  const [state, setState] = useState("READY");

  async function run(command) {
    setState(`RUNNING · ${command[0]}`);
    try {
      const result = await dispatchTool(command[1]);
      setState(`${command[0]} · ${String(result?.status || "ROUTED").toUpperCase()}`);
    } catch (error) {
      setState(`${command[0]} · ERROR: ${error.message}`);
    }
  }

  return (
    <section className="cc-quick">
      <div className="cc-quick-head">
        <span className="cc-eyebrow">QUICK COMMANDS</span>
        <strong>{state}</strong>
      </div>
      <div className="cc-quick-grid">
        {commands.map(command => (
          <button key={command[0]} onClick={() => run(command)}>{command[0]}</button>
        ))}
      </div>
    </section>
  );
}

function ActiveTasks({ tasks = [] }) {
  const active = tasks.filter(t => !["COMPLETED", "FAILED"].includes(String(t.status || "").toUpperCase())).slice(0, 4);
  return (
    <div className="cc-task-list">
      {active.map((task, index) => {
        const value = pct(task.progress);
        return (
          <div className="cc-task" key={task.id}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div><strong>{task.title || "Untitled task"}</strong><div className="cc-meter"><i style={value == null ? undefined : { width: `${value}%` }} /></div></div>
            <b>{value == null ? "N/A" : `${value}%`}</b>
          </div>
        );
      })}
      {!active.length && <span className="cc-empty">NO ACTIVE TASKS</span>}
    </div>
  );
}

export default function DashboardHome({
  system,
  connectionState = "CONNECTING",
  lastRefreshAt = null,
  agents = [],
  radarFindings = [],
  tasks = [],
  memories = [],
  activities = [],
  gmailStatus = null,
  coreState = "IDLE",
  working = false,
  onRefresh,
  telemetryHistory = [],
  onState,
  onModToggle,
  onPowerCommand,
  onOpenMap,
}) {
  const telemetry = system?.telemetry || {};
  const services = system?.services || {};
  const uptime = formatUptime(telemetry.uptime_seconds);
  const activeCount = tasks.filter(t => !["COMPLETED", "FAILED"].includes(String(t.status || "").toUpperCase())).length;
  const lastActivity = activities[0];

  const topReadout = useMemo(() => ({
    model: system?.ai?.model || "N/A",
    tier: system?.ai?.tier || "N/A",
    status: services.ai_core || "NOT_CONFIGURED",
    uptime,
    active: activeCount,
  }), [system, services.ai_core, uptime, activeCount]);

  return (
    <div className={`command-center-reference ${working ? "cc-working" : "cc-normal"}`}>
      <div className="cc-titlebar">
        <div className="cc-logo">MR AI</div>
        <div className="cc-title">MR AI COMMAND CENTER</div>
        <div className="cc-clock-state"><span>{working ? "WORKING MODE" : "NORMAL MODE"}</span><strong>{connectionState === "ONLINE" ? "● ONLINE" : connectionState}</strong></div>
      </div>

      <div className="cc-top-grid">
        <Panel eyebrow="SYSTEM STATUS" title="System Status">
          <SystemStatus
            telemetry={telemetry}
            telemetryHistory={telemetryHistory}
            connectionState={connectionState}
            lastRefreshAt={lastRefreshAt}
            onRefresh={onRefresh}
          />
        </Panel>

        <Panel eyebrow="AI CORE STATUS" title="AI Core Status" badge={coreState}>
          <div className="cc-core-status">
            <div className="cc-core-readout">
              <div><span>AI MODEL</span><strong>{topReadout.model}</strong></div>
              <div><span>AI TIER</span><strong>{topReadout.tier}</strong></div>
              <div><span>AI RUNTIME</span><strong>{system?.ai?.ready ? "READY" : "NOT READY"}</strong></div>
              <div><span>UPTIME</span><strong>{topReadout.uptime}</strong></div>
              <div><span>STATUS</span><strong>{topReadout.status}</strong></div>
              <div><span>TASKS</span><strong>{topReadout.active}</strong></div>
            </div>
            <Core state={coreState} modActive={working} />
          </div>
        </Panel>

        <Panel eyebrow="MISSION OVERVIEW" title="Mission Overview">
          <MissionOverview tasks={tasks} />
        </Panel>
      </div>

      <div className="cc-main-grid">
        <Panel eyebrow="RADAR SCAN" title="Radar Scan" badge={`${radarFindings.length} CONTACTS`}>
          <Radar findings={radarFindings} />
        </Panel>

        <Panel eyebrow="GLOBAL NETWORK" title="World Monitoring">
          <HolographicWorldMap onOpenMap={onOpenMap} />
        </Panel>

        <Panel eyebrow="MR AI CHAT" title="MR AI Chat" className="cc-chat-panel">
          <Chat onState={onState} onModToggle={onModToggle} onPowerCommand={onPowerCommand} />
        </Panel>

        <Panel eyebrow="WEB RESEARCH" title="Web Research">
          <WebResearch />
        </Panel>
      </div>

      <QuickCommands />

      <div className="cc-bottom-strip">
        <div><span>AGENTS</span><strong>{agents.length}</strong></div>
        <div><span>MEMORY</span><strong>{memories.length}</strong></div>
        <div><span>LAST ACTIVITY</span><strong>{lastActivity ? `${lastActivity.action || "EVENT"} · ${formatTime(lastActivity.created_at || lastActivity.timestamp)}` : "NONE"}</strong></div>
        <div><span>BROWSER</span><strong>{services.extension || "NOT_CONNECTED"}</strong></div>
        <div><span>GMAIL</span><strong>{gmailStatus?.status || services.gmail || "NOT_CONNECTED"}</strong></div>
      </div>

      <div className="cc-footerline">
        <span>OWNER // BOSS FERISI</span>
        <span>MANAGER // MR AI</span>
        <span>WORKSPACE // MOG343</span>
        <span>AUTHORIZED RUNTIME DATA ONLY</span>
      </div>
    </div>
  );
}
