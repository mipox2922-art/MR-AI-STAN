import { useMemo, useState } from "react";
import { dispatchTool, searchToolWeb } from "../api";
import Core from "./Core";
import Chat from "./Chat";
import LiveGoogleMap from "./LiveGoogleMap";

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

function formatDashboardDate(value) {
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) return "--";
  return value.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric" }).toUpperCase();
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

  const sparkValues = telemetryHistory.slice(-10).map(item => {
    const sent = Number(item?.network?.bytes_sent);
    const received = Number(item?.network?.bytes_received);
    return Number.isFinite(sent) && Number.isFinite(received) ? sent + received : null;
  }).filter(value => value !== null);
  const maxSpark = sparkValues.length ? Math.max(...sparkValues) : 1;
  const minSpark = sparkValues.length ? Math.min(...sparkValues) : 0;
  const sparkPoints = sparkValues.length > 1
    ? sparkValues.map((value, index) => {
        const x = 2 + (index / (sparkValues.length - 1)) * 96;
        const range = Math.max(1, maxSpark - minSpark);
        const y = 26 - ((value - minSpark) / range) * 20;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ")
    : "";

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
      <div className="cc-network-spark">
        <svg viewBox="0 0 100 28" preserveAspectRatio="none" aria-label="Network traffic history">
          {sparkPoints && <polyline points={sparkPoints} fill="none" stroke="var(--accent)" strokeWidth="1.1" />}
        </svg>
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
      <div className="cc-mission-globe" aria-hidden="true">
        <div className="cc-globe-ring ring-a" />
        <div className="cc-globe-ring ring-b" />
        <div className="cc-globe-arc arc-a" />
        <div className="cc-globe-arc arc-b" />
        <div className="cc-globe-gridline grid-h" />
        <div className="cc-globe-gridline grid-v" />
      </div>
      <div className="cc-mission-stats">
        <div><span>ACTIVE</span><strong>{active.length}</strong></div>
        <div><span>DONE</span><strong>{completed}</strong></div>
        <div><span>TOTAL</span><strong>{tasks.length}</strong></div>
      </div>
    </div>
  );
}

function stableHash(value) {
  return Array.from(String(value || "")).reduce((hash, char) => (
    (hash * 31 + char.charCodeAt(0)) >>> 0
  ), 7);
}

function radarRadius(finding) {
  const distance = Number(finding?.distance_estimate_m);
  if (Number.isFinite(distance)) return Math.max(14, Math.min(44, 12 + distance * 0.28));
  const signalText = String(finding?.signal ?? "").replace("%", "");
  const signal = Number(signalText);
  if (Number.isFinite(signal)) return Math.max(12, Math.min(44, 46 - signal * 0.28));
  return 28;
}

function Radar({ findings = [], onRadarScan }) {
  const points = findings.slice(0, 18);
  const [scanState, setScanState] = useState("READY");

  const counts = {
    wifi: points.filter(item => item?.type === "wifi").length,
    bluetooth: points.filter(item => item?.type === "bluetooth").length,
    android: points.filter(item => item?.type === "android").length,
    fastboot: points.filter(item => item?.type === "fastboot").length,
  };

  async function runScan(source) {
    if (!onRadarScan) return;
    setScanState(`SCANNING · ${source.toUpperCase()}`);
    try {
      await onRadarScan(source);
      setScanState(`${source.toUpperCase()} · COMPLETE`);
    } catch (error) {
      setScanState(`${source.toUpperCase()} · ERROR`);
    }
  }

  const scanButtons = ["all", "wifi", "bluetooth", "android", "fastboot"];

  return (
    <div className="cc-radar-wrap">
      <div className="cc-radar-controls" role="group" aria-label="Radar scan controls">
        {scanButtons.map(source => (
          <button
            key={source}
            className={source === "all" ? "active" : ""}
            onClick={() => runScan(source)}
            disabled={scanState.startsWith("SCANNING")}
          >
            {source === "all" ? "SCAN ALL" : source === "bluetooth" ? "BLE SCAN" : `${source.toUpperCase()} SCAN`}
          </button>
        ))}
      </div>
      <div className="cc-radar-shell">
        <div className="cc-radar">
          <div className="cc-radar-cross cross-x" />
          <div className="cc-radar-cross cross-y" />
          <div className="cc-radar-ring ring-1" />
          <div className="cc-radar-ring ring-2" />
          <div className="cc-radar-ring ring-3" />
          <div className="cc-radar-ring ring-4" />
          <div className="cc-radar-sweep" />
          <div className="cc-radar-origin" />
          <div className="cc-radar-corner corner-tl" />
          <div className="cc-radar-corner corner-tr" />
          <div className="cc-radar-corner corner-bl" />
          <div className="cc-radar-corner corner-br" />
          {points.map((finding, index) => {
            const seed = stableHash(finding.id || finding.address || finding.label || (finding.type + "-" + index));
            const angle = (seed % 360) * (Math.PI / 180);
            const radius = radarRadius(finding);
            const left = 50 + Math.cos(angle) * radius;
            const top = 50 + Math.sin(angle) * radius;
            return (
              <span
                key={finding.id || finding.address || finding.label || index}
                className="cc-radar-contact"
                style={{ left: left + "%", top: top + "%", animationDelay: (index % 6) * 120 + "ms" }}
                title={finding.label || finding.address || finding.type || "Sensor contact"}
              ><i /></span>
            );
          })}
          <div className="cc-radar-core">MR</div>
        </div>
        <div className="cc-radar-scale scale-top">100 KM</div>
        <div className="cc-radar-scale scale-right">75 KM</div>
        <div className="cc-radar-scale scale-bottom">50 KM</div>
        <div className="cc-radar-scale scale-left">25 KM</div>
      </div>
      <div className="cc-radar-info">
        <div className="cc-radar-contact-count">
          <span>CONTACTS</span><strong>{points.length}</strong>
          <small>{findings.length ? "VERIFIED SENSOR FINDINGS" : "NO SENSOR DATA"}</small>
        </div>
        <div className="cc-radar-source">
          <div><span>WI-FI</span><strong>{counts.wifi}</strong></div>
          <div><span>BLE</span><strong>{counts.bluetooth}</strong></div>
          <div><span>ANDROID</span><strong>{counts.android}</strong></div>
          <div><span>FASTBOOT</span><strong>{counts.fastboot}</strong></div>
        </div>
      </div>
      <div className="cc-radar-status"><span>{scanState}</span><strong>{findings.length ? "LIVE SENSOR SNAPSHOT" : "WAITING FOR SENSOR SCAN"}</strong></div>
      <div className="cc-radar-note">CONTACT PLOT IS A VISUAL PROXIMITY VIEW. DIRECTION IS NOT CLAIMED WITHOUT DIRECTIONAL SENSOR DATA.</div>
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
      const data = await searchToolWeb(value);
      setResults(Array.isArray(data?.results) ? data.results.slice(0, 4) : []);
      setStatus(String(data?.status || "UNKNOWN").toUpperCase());
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
    ["⌕", "SCAN SYSTEM", "scan my system status"],
    ["◫", "ANALYZE DATA", "analyze my current system data"],
    ["◎", "WEB RESEARCH", "research the latest technology trends"],
    ["▣", "GENERATE REPORT", "generate a concise executive report of my current system"],
    ["◈", "SECURITY CHECK", "run a security status check"],
    ["⚙", "OPTIMIZE", "identify safe optimization opportunities"],
  ];
  const [state, setState] = useState("READY");

  async function run(command) {
    setState(`RUNNING · ${command[1]}`);
    try {
      const result = await dispatchTool(command[1]);
      setState(`${command[1]} · ${String(result?.status || "ROUTED").toUpperCase()}`);
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
          <button key={command[1]} onClick={() => run(command)}>
            <span>{command[0]}</span>
            <strong>{command[1]}</strong>
          </button>
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
  onRadarScan,
  clock = null,
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
        <div className="cc-brand-lockup">
          <div className="cc-logo">MR AI</div>
          <div className="cc-title">COMMAND CENTER</div>
        </div>
        <div className="cc-mode-chip">
          <span className="cc-mode-dot" />
          <strong>{working ? "WORKING MODE" : "NORMAL MODE"}</strong>
        </div>
        <div className="cc-header-right">
          <div className="cc-header-clock">
            <strong>{clock ? clock.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--:--:--"}</strong>
            <span>{formatDashboardDate(clock)}</span>
          </div>
          <div className="cc-header-operator">
            <strong>BOSS FERISI</strong>
            <span>CHIEF OF STAFF</span>
            <small>{connectionState === "ONLINE" ? "● ONLINE" : connectionState}</small>
          </div>
        </div>
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
          <Radar findings={radarFindings} onRadarScan={onRadarScan} />
        </Panel>

        <Panel eyebrow="LIVE MAP" title="OpenStreetMap + Street View">
          <LiveGoogleMap />
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
