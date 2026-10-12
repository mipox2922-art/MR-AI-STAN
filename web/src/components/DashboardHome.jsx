import { useMemo, useState } from "react";
import { dispatchTool, searchToolWeb, planAgentWork, executeMission } from "../api";
import Core from "./Core";
import Chat from "./Chat";
import LiveMap from "./LiveMap";

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function pct(value) {
  const n = finiteNumber(value);
  return n === null ? null : Math.max(0, Math.min(100, n));
}

function formatUptime(seconds) {
  const n = finiteNumber(seconds);
  if (n === null) return "N/A";
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
  const n = finiteNumber(value);
  if (n === null) return "N/A";
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(2)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${Math.round(n)} B`;
}

function formatRate(bytesPerSecond) {
  if (finiteNumber(bytesPerSecond) === null || bytesPerSecond < 0) return "WAITING";
  return `${formatBytes(bytesPerSecond)}/s`;
}

function NetworkMetric({ telemetry, telemetryHistory = [] }) {
  const currentSent = finiteNumber(telemetry?.network?.bytes_sent);
  const currentReceived = finiteNumber(telemetry?.network?.bytes_received);
  const previous = telemetryHistory.length > 1 ? telemetryHistory[telemetryHistory.length - 2] : null;
  const previousSent = finiteNumber(previous?.network?.bytes_sent);
  const previousReceived = finiteNumber(previous?.network?.bytes_received);
  const elapsedSeconds = previous?.captured_at
    ? Math.max(0.1, (Date.now() - Number(previous.captured_at)) / 1000)
    : null;

  const txRate = previous && elapsedSeconds && currentSent !== null && previousSent !== null
    ? Math.max(0, currentSent - previousSent) / elapsedSeconds
    : null;
  const rxRate = previous && elapsedSeconds && currentReceived !== null && previousReceived !== null
    ? Math.max(0, currentReceived - previousReceived) / elapsedSeconds
    : null;

  const sparkValues = telemetryHistory.slice(-10).map(item => {
    const sent = finiteNumber(item?.network?.bytes_sent);
    const received = finiteNumber(item?.network?.bytes_received);
    return sent !== null && received !== null ? sent + received : null;
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
      <Metric label="BACKEND CPU" value={telemetry?.cpu_percent} />
      <Metric label="BACKEND MEMORY" value={telemetry?.memory_percent} />
      <NetworkMetric telemetry={telemetry} telemetryHistory={telemetryHistory} />
      <Metric label="BACKEND STORAGE" value={telemetry?.storage_percent} />
      <Metric label="GPU" value={telemetry?.gpu?.utilization_percent} />
      <div className="cc-telemetry-source">
        {telemetry?.source === "host_runtime"
          ? "BACKEND HOST TELEMETRY · NOT PERSONAL PC SENSOR DATA"
          : telemetry?.source === "serverless_runtime"
            ? "HOST METRICS UNAVAILABLE IN THIS RUNTIME"
            : "WAITING FOR TELEMETRY SOURCE"}
      </div>
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
  const distance = finiteNumber(finding?.distance_estimate_m);
  if (distance !== null) {
    // Measured/estimated range only affects the schematic radius; it does not infer bearing.
    return Math.max(12, Math.min(44, 12 + Math.log10(Math.max(0, distance) + 1) * 12));
  }
  const signal = finiteNumber(String(finding?.signal ?? "").replace("%", ""));
  if (signal !== null) {
    // RSSI is normally negative dBm; Wi-Fi percentages are 0..100.
    const strength = signal < 0
      ? Math.max(0, Math.min(100, ((signal + 100) / 65) * 100))
      : Math.max(0, Math.min(100, signal));
    return 44 - (strength / 100) * 32;
  }
  return 28;
}

function Radar({ findings = [], onRadarScan }) {
  const points = findings.slice(0, 18);
  const [scanState, setScanState] = useState("READY");
  const [scanError, setScanError] = useState("");

  const counts = {
    wifi: points.filter(item => item?.type === "wifi").length,
    bluetooth: points.filter(item => item?.type === "bluetooth").length,
    android: points.filter(item => item?.type === "android").length,
    fastboot: points.filter(item => item?.type === "fastboot").length,
  };

  async function runScan(source) {
    if (!onRadarScan) return;
    setScanError("");
    setScanState(`SCANNING · ${source.toUpperCase()}`);
    try {
      const result = await onRadarScan(source);
      setScanState(`${source.toUpperCase()} · COMPLETE`);
      if (Array.isArray(result?.findings) && result.findings.length === 0) {
        setScanError("Scan completed but no contacts were returned by the connected sensor.");
      }
    } catch (error) {
      setScanState(`${source.toUpperCase()} · ERROR`);
      setScanError(error?.message || "The sensor scan failed.");
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
        <div className="cc-radar-scale scale-top">OUTER RING</div>
        <div className="cc-radar-scale scale-right">BEARING N/A</div>
        <div className="cc-radar-scale scale-bottom">INNER RING</div>
        <div className="cc-radar-scale scale-left">RANGE N/A</div>
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
      <div className="cc-radar-contact-list" aria-live="polite">
        {points.length ? points.slice(0, 4).map((finding, index) => {
          const rawSignal = finiteNumber(finding?.signal);
          const distance = finiteNumber(finding?.distance_estimate_m);
          const signalText = rawSignal === null ? "SIGNAL N/A" : `SIGNAL ${rawSignal}${rawSignal >= 0 ? "%" : " dBm"}`;
          const rangeText = distance === null ? "RANGE NOT MEASURED" : `EST. ${distance.toFixed(1)} m · ${String(finding?.distance_confidence || "LOW").toUpperCase()} CONFIDENCE`;
          return (
            <div className="cc-radar-contact-row" key={finding.id || finding.address || finding.label || index}>
              <span className={`cc-contact-type type-${String(finding.type || "unknown").toLowerCase()}`}>{String(finding.type || "sensor").toUpperCase()}</span>
              <div><strong>{finding.label || finding.address || "Unnamed contact"}</strong><small>{finding.source || "LOCAL SENSOR"} · {signalText}</small></div>
              <small>{rangeText}</small>
            </div>
          );
        }) : (
          <div className="cc-radar-empty">
            <strong>NO VERIFIED CONTACTS</strong>
            <span>Radar needs the MR AI Device Bridge running on your computer for Wi-Fi, Bluetooth, ADB and Fastboot scans. The hosted website cannot scan nearby devices by itself.</span>
          </div>
        )}
      </div>
      <div className="cc-radar-status"><span>{scanState}</span><strong>{findings.length ? "SENSOR RESULTS RECEIVED" : "NO SENSOR RESULTS"}</strong></div>
      {scanError && <div className="cc-radar-error" role="status">{scanError}</div>}
      <div className="cc-radar-note">CONTACT POSITIONS ARE SCHEMATIC ONLY. NO DIRECTION OR DISTANCE IS CLAIMED UNLESS THE SENSOR RETURNS A MEASUREMENT.</div>
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
      setState(`${command[1]} · ERROR: ${error.message}`);
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

function statusLabel(value) {
  return String(value || "READY").replaceAll("_", " ").replaceAll("-", " ");
}

function isTaskActive(task) {
  return !["COMPLETED", "FAILED", "CANCELLED"].includes(String(task?.status || "").toUpperCase());
}

function AgentFleet({ agents = [], tasks = [], missionSnapshot = null, onOpenAgents }) {
  const steps = Array.isArray(missionSnapshot?.steps)
    ? missionSnapshot.steps
    : Array.isArray(missionSnapshot?.plan?.steps)
      ? missionSnapshot.plan.steps
      : [];
  const activeTaskCount = tasks.filter(isTaskActive).length;
  const waitingCount = steps.filter(step => String(step.status || "").toUpperCase().includes("WAITING")).length;

  return (
    <div className="cc-agent-fleet-wrap">
      <div className="cc-agent-fleet-summary">
        <div><span>REGISTERED</span><strong>{agents.length}</strong></div>
        <div><span>ACTIVE TASKS</span><strong>{activeTaskCount}</strong></div>
        <div><span>MISSION STEPS</span><strong>{steps.length}</strong></div>
        <div><span>WAITING / HANDOFF</span><strong>{waitingCount}</strong></div>
      </div>
      <div className="cc-agent-fleet-grid">
        {agents.map(agent => {
          const id = String(agent.id || "").toLowerCase();
          const name = String(agent.name || id);
          const assigned = tasks.filter(task => {
            const owner = String(task.agent || "").toLowerCase().trim();
            return owner === id || owner === name.toLowerCase() || owner.replaceAll(" ", "_") === id;
          });
          const task = assigned.find(isTaskActive) || assigned[0];
          const step = [...steps].reverse().find(item => String(item.agent || "").toLowerCase() === id);
          let state = "STANDBY";
          let currentWork = "No task assigned";
          if (step) {
            state = statusLabel(step.status);
            currentWork = step.evidence?.message || step.tool || (Array.isArray(step.tools) ? step.tools.slice(0, 2).join(" · ") : "") || "Mission step assigned";
          } else if (task) {
            state = statusLabel(task.status);
            currentWork = task.title || "Assigned task";
          }
          const statusClass = state.toLowerCase().replaceAll(" ", "-");
          return (
            <article className="cc-agent-tile" key={agent.id}>
              <div className="cc-agent-tile-top">
                <span className="cc-agent-glyph">{id === "device" ? "⌁" : id === "creative" ? "✦" : id === "research" ? "◎" : id === "security" ? "◈" : id === "orchestrator" ? "MR" : "◆"}</span>
                <span className={`cc-agent-state state-${statusClass}`}>{state}</span>
              </div>
              <strong className="cc-agent-name">{name}</strong>
              <p>{agent.description || "Registered specialist agent."}</p>
              <div className="cc-agent-current"><span>CURRENT WORK</span><strong>{currentWork}</strong></div>
              <div className="cc-agent-capabilities">{(agent.capabilities || []).slice(0, 3).join(" · ")}</div>
            </article>
          );
        })}
      </div>
      {!agents.length && <div className="cc-agent-empty">Agent registry could not be loaded. Check backend connection and refresh the dashboard.</div>}
      <button type="button" className="cc-inline-button cc-agent-open" onClick={onOpenAgents}>OPEN FULL AGENT CONTROL →</button>
      <p className="cc-agent-legend">STANDBY means registered but not assigned active work. WAITING means a permissioned integration or device/browser hand is required.</p>
    </div>
  );
}

function MissionWorkbench({ onMissionUpdate }) {
  const [request, setRequest] = useState("");
  const [planResult, setPlanResult] = useState(null);
  const [missionResult, setMissionResult] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const current = missionResult || planResult;
  const steps = Array.isArray(missionResult?.steps)
    ? missionResult.steps
    : Array.isArray(planResult?.steps)
      ? planResult.steps
      : [];

  async function createPlan(event) {
    event?.preventDefault();
    const value = request.trim();
    if (!value || busy) return;
    setBusy("PLAN");
    setError("");
    setMissionResult(null);
    try {
      const result = await planAgentWork(value);
      setPlanResult(result);
      onMissionUpdate?.(result);
    } catch (err) {
      setError(err?.message || "Unable to build a mission plan.");
    } finally {
      setBusy("");
    }
  }

  async function runMission() {
    const value = request.trim();
    if (!value || busy) return;
    setBusy("RUN");
    setError("");
    try {
      const result = await executeMission(value);
      setMissionResult(result);
      if (result?.plan) setPlanResult(result.plan);
      onMissionUpdate?.(result);
    } catch (err) {
      setError(err?.message || "Mission could not be started.");
    } finally {
      setBusy("");
    }
  }

  const examples = [
    "Kagua afya ya mfumo wa MR AI",
    "Tafuta ajira za remote za Python na React",
    "Chambua repo ya MR-AI-STAN kwa makosa",
  ];

  return (
    <div className="cc-workbench">
      <div className="cc-workbench-intro">
        <p>Andika kazi unayotaka MR AI ifanye. Panga kwanza ili kuona agents watakaohusika; endesha mission ili runtime ijaribu hatua zinazoungwa mkono. Hatua zinazohitaji browser/device integration zitaonyeshwa kama WAITING badala ya kudai zimekamilika.</p>
      </div>
      <form className="cc-mission-form" onSubmit={createPlan}>
        <label htmlFor="cc-mission-request">MISSION / LENGO LA BOSS FERISI</label>
        <input
          id="cc-mission-request"
          value={request}
          onChange={event => setRequest(event.target.value)}
          placeholder="Mfano: kagua mfumo, tafuta taarifa, au panga mradi wangu..."
          maxLength={1000}
          required
        />
        <div className="cc-mission-actions">
          <button type="submit" disabled={Boolean(busy) || !request.trim()}>{busy === "PLAN" ? "INAPANGA..." : "PLAN MISSION"}</button>
          <button type="button" className="primary-button" disabled={Boolean(busy) || !request.trim()} onClick={runMission}>{busy === "RUN" ? "INAENDESHA..." : "RUN MISSION"}</button>
        </div>
      </form>
      <div className="cc-mission-examples">
        <span>QUICK START</span>
        {examples.map(example => <button type="button" key={example} onClick={() => setRequest(example)}>{example}</button>)}
      </div>
      {error && <div className="cc-workbench-error" role="alert">{error}</div>}
      {current ? (
        <div className="cc-mission-result" aria-live="polite">
          <div className="cc-mission-result-head">
            <div><span>MISSION STATE</span><strong>{statusLabel(missionResult?.status || planResult?.status || "PLANNED")}</strong></div>
            {missionResult?.mission?.id && <div><span>MISSION ID</span><strong>#{missionResult.mission.id}</strong></div>}
            {missionResult?.mission?.progress !== undefined && <div><span>PROGRESS</span><strong>{missionResult.mission.progress}%</strong></div>}
          </div>
          {steps.length ? (
            <div className="cc-mission-steps">
              {steps.map((step, index) => (
                <div className="cc-mission-step" key={step.step || `${step.agent}-${index}`}>
                  <span className="cc-step-number">{String(step.step || index + 1).padStart(2, "0")}</span>
                  <div><strong>{step.name || step.agent || "Agent step"}</strong><small>{step.tool || (Array.isArray(step.tools) ? step.tools.slice(0, 3).join(" · ") : "") || (Array.isArray(step.capabilities) ? step.capabilities.slice(0, 3).join(" · ") : "Waiting for runtime details")}</small></div>
                  <span className={`cc-agent-state state-${statusLabel(step.status).toLowerCase().replaceAll(" ", "-")}`}>{statusLabel(step.status)}</span>
                </div>
              ))}
            </div>
          ) : <p className="cc-agent-empty">Plan returned no specialist steps.</p>}
          {missionResult?.next_action && <div className="cc-next-action"><strong>NEXT ACTION</strong><span>{missionResult.next_action}</span></div>}
        </div>
      ) : (
        <div className="cc-workbench-empty"><strong>WAITING FOR YOUR MISSION</strong><span>Agent plan and run evidence will appear here. Nothing runs until you press a mission button.</span></div>
      )}
    </div>
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
  onOpenAgents,
  onRadarScan,
  clock = null,
}) {
  const [missionSnapshot, setMissionSnapshot] = useState(null);
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
          <div className="cc-header-tools" aria-hidden="true">
            <span>♧</span>
            <span>⌁</span>
            <span>◌</span>
          </div>
          <div className="cc-header-clock">
            <strong>{clock ? clock.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--:--:--"}</strong>
            <span>{formatDashboardDate(clock)}</span>
          </div>
          <div className="cc-header-operator">
            <div className="cc-header-avatar">MR</div>
            <div>
              <strong>BOSS FERISI</strong>
              <span>CHIEF OF STAFF</span>
              <small>{connectionState === "ONLINE" ? "● ONLINE" : connectionState}</small>
            </div>
          </div>
        </div>
      </div>

      <div className="cc-top-grid">
        <Panel eyebrow="BACKEND TELEMETRY" title="Runtime Status">
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

      <div className="cc-operations-grid">
        <Panel eyebrow="MISSION CONTROL" title="Mission Workbench">
          <MissionWorkbench onMissionUpdate={setMissionSnapshot} />
        </Panel>
        <Panel
          eyebrow="AGENT CREW"
          title="Specialist Fleet"
          badge={`${agents.length} REGISTERED`}
          action={<button type="button" className="cc-inline-button" onClick={onOpenAgents}>AGENT CONTROL</button>}
        >
          <AgentFleet agents={agents} tasks={tasks} missionSnapshot={missionSnapshot} onOpenAgents={onOpenAgents} />
        </Panel>
      </div>

      <div className="cc-main-grid">
        <Panel eyebrow="RADAR SCAN" title="Radar Scan" badge={`${radarFindings.length} CONTACTS`}>
          <Radar findings={radarFindings} onRadarScan={onRadarScan} />
        </Panel>

        <Panel eyebrow="LIVE MAP" title="OpenStreetMap + Street View">
          <LiveMap />
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
