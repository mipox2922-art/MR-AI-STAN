import { useEffect, useMemo, useState } from "react";
import { dispatchTool, searchToolWeb, planAgentWork, executeMission, chat, getExecutiveBriefing, browserNavigate, browserClick, browserType, browserScroll, browserDrag, getCurrentPage, reportMissionHandoff } from "../api";
import HudOrb from "./HudOrb";
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
  const refreshLabel = lastRefreshAt
    ? new Date(lastRefreshAt).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "WAITING";

  return (
    <div className="cc-system-status">
      <div className="cc-system-layout">
        <div className="cc-system-metrics">
          <Metric label="CPU Usage · BACKEND" value={telemetry?.cpu_percent} />
          <Metric label="Memory · BACKEND" value={telemetry?.memory_percent} />
          <Metric label="Storage · BACKEND" value={telemetry?.storage_percent} />
          <Metric label="GPU" value={telemetry?.gpu?.utilization_percent} />
        </div>
        <div className="cc-system-network">
          <span className="cc-system-network-title">NETWORK TRAFFIC</span>
          <NetworkMetric telemetry={telemetry} telemetryHistory={telemetryHistory} />
          <div className="cc-network-summary">
            <span>TX {Number.isFinite(Number(telemetry?.network?.bytes_sent)) ? formatBytes(telemetry.network.bytes_sent) : "N/A"}</span>
            <span>RX {Number.isFinite(Number(telemetry?.network?.bytes_received)) ? formatBytes(telemetry.network.bytes_received) : "N/A"}</span>
          </div>
        </div>
      </div>
      <div className="cc-telemetry-source">
        {telemetry?.source === "host_runtime"
          ? "BACKEND HOST TELEMETRY · NOT PERSONAL PC SENSOR DATA"
          : telemetry?.source === "serverless_runtime"
            ? "HOST METRICS UNAVAILABLE IN THIS RUNTIME"
            : "WAITING FOR TELEMETRY SOURCE"}
      </div>
      <div className="cc-system-footer">
        <span>RUNTIME · {connectionState || "CONNECTING"} · {refreshLabel}</span>
        <strong>AUTHORIZED RUNTIME DATA ONLY</strong>
      </div>
      <button className="cc-inline-button" onClick={onRefresh}>REFRESH TELEMETRY</button>
    </div>
  );
}

function MissionOverview({ tasks = [] }) {
  const active = tasks.filter(t => !["COMPLETED", "FAILED"].includes(String(t.status || "").toUpperCase()));
  const values = active.slice(0, 16).map(t => pct(t.progress)).filter(v => v !== null);
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
        <p>Muhtasari wa kazi zilizorekodiwa na maendeleo yaliyothibitishwa.</p>
        <span>KAZI INAYOANGALIWA</span>
        <strong>{focus === "NO ACTIVE MISSION" ? "Hakuna kazi inayoendelea" : focus}</strong>
        <small className="cc-mission-summary">{active.length} ZINAENDELEA · {tasks.length} JUMLA</small>
      </div>
      <div className="cc-mission-graph">
        <div className="cc-graph-grid" />
        <svg viewBox="0 0 100 50" preserveAspectRatio="none" aria-label="Verified task progress history">
          {chart && <polyline points={chart} fill="none" stroke="var(--c)" strokeWidth="1.2" />}
          {values.map((v, i) => {
            const x = values.length === 1 ? 8 : 8 + (i / (values.length - 1)) * 84;
            const y = 45 - v * 0.36;
            return <circle key={i} cx={x} cy={y} r="1.35" fill="var(--c)" />;
          })}
        </svg>
        {!chart && <span className="cc-chart-empty">Hakuna maendeleo ya kazi yaliyorekodiwa bado</span>}
        <div className="cc-chart-axis"><span>00</span><span>04</span><span>08</span><span>12</span><span>16</span><span>20</span><span>24</span></div>
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

function Radar({ findings = [], onRadarScan, sensorStatus = {}, onOpenDevice }) {
  const points = findings.slice(0, 18);
  const [scanState, setScanState] = useState("READY");
  const [scanError, setScanError] = useState("");

  const counts = {
    wifi: findings.filter(item => item?.type === "wifi").length,
    bluetooth: findings.filter(item => item?.type === "bluetooth").length,
    android: findings.filter(item => item?.type === "android").length,
    fastboot: findings.filter(item => item?.type === "fastboot").length,
  };

  async function runScan(source) {
    if (!onRadarScan || scanState.startsWith("SCANNING")) return;
    setScanError("");
    setScanState(`SCANNING · ${source.toUpperCase()}`);
    try {
      const result = await onRadarScan(source);
      setScanState(`${source.toUpperCase()} · COMPLETE`);
      if (!["data", "radio"].includes(source)) {
        const statusKey = source === "all" ? null : source;
        const sourceStatus = statusKey ? result?.sensor_status?.[statusKey] : null;
        const count = Number.isFinite(Number(sourceStatus?.count))
          ? Number(sourceStatus.count)
          : Array.isArray(result?.findings) ? result.findings.length : 0;
        if (count === 0) {
          setScanError(`${source.toUpperCase()} scan returned zero contacts. Check sensor availability and local Device Bridge permissions.`);
        }
      }
    } catch (error) {
      setScanState(`${source.toUpperCase()} · ERROR`);
      setScanError(error?.message || "The sensor scan failed.");
    }
  }

  const scanButtons = ["all", "wifi", "bluetooth", "android", "fastboot", "radio", "data"];
  const channels = [
    { key: "wifi", label: "WI-FI", icon: "⌁", count: counts.wifi },
    { key: "bluetooth", label: "BLUETOOTH", icon: "ᛒ", count: counts.bluetooth },
    { key: "android", label: "ANDROID", icon: "▣", count: counts.android },
    { key: "fastboot", label: "FASTBOOT", icon: "⇅", count: counts.fastboot },
    { key: "data", label: "DATA LINK", icon: "⇅", count: null },
    { key: "radio", label: "RADIO / RF", icon: "〰", count: null },
  ];

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
            {source === "all" ? "SCAN ALL" : source === "bluetooth" ? "BLE SCAN" : source === "radio" ? "RADIO / RF" : source === "data" ? "DATA LINK" : `${source.toUpperCase()} SCAN`}
          </button>
        ))}
      </div>

      <div className="cc-radar-overview">
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
          <span className="cc-radar-scale scale-top">SCAN RANGE</span>
          <span className="cc-radar-scale scale-bottom">LOCAL SENSORS</span>
        </div>

        <div className="cc-radar-info">
          <div className="cc-radar-contact-count">
            <span>CONTACTS</span>
            <strong>{findings.length}</strong>
            <small>{findings.length ? "SENSOR FINDINGS" : "NO SENSOR DATA"}</small>
          </div>
          <div className="cc-radar-source">
            <div><span>WI-FI</span><strong>{counts.wifi}</strong></div>
            <div><span>BLE</span><strong>{counts.bluetooth}</strong></div>
            <div><span>ANDROID</span><strong>{counts.android}</strong></div>
            <div><span>FASTBOOT</span><strong>{counts.fastboot}</strong></div>
          </div>
        </div>
      </div>

      <div className="cc-radar-status"><span>{scanState}</span><strong>{findings.length ? "SENSOR RESULTS RECEIVED" : "NO SENSOR RESULTS"}</strong></div>
      {scanError && <div className="cc-radar-error" role="status">{scanError}</div>}
      <details className="cc-radar-details">
        <summary><strong>SENSOR DETAILS</strong><span>{findings.length ? `${findings.length} CONTACTS` : "NO SENSOR DATA"} · 6 CHANNELS</span></summary>
      <div className="cc-radar-channels">
        {channels.map(channel => {
          const value = sensorStatus[channel.key] || {};
          const rawStatus = String(value.status || "NOT SCANNED").toUpperCase();
          let label = rawStatus.replaceAll("_", " ");
          if (channel.key === "data" && value.type) label += ` · ${String(value.type).toUpperCase()}`;
          if (channel.count !== null && Number.isFinite(Number(value.count))) label += ` · ${Number(value.count)} FOUND`;
          const good = /^(ONLINE|CONNECTED|SCANNED|AVAILABLE|VERIFIED|READY)$/.test(rawStatus);
          const warn = /NOT_|UNAVAILABLE|OFFLINE|ERROR|DENIED|FAILED/.test(rawStatus);
          return (
            <div className="cc-radar-channel" key={channel.key}>
              <div className="cc-radar-channel-head"><span>{channel.icon}</span><strong>{channel.label}</strong></div>
              <b className={good ? "channel-good" : warn ? "channel-warn" : "channel-neutral"}>{label}</b>
            </div>
          );
        })}
      </div>

      {points.length > 0 ? (
        <div className="cc-radar-contact-list" aria-live="polite">
          {points.slice(0, 3).map((finding, index) => {
            const rawSignal = finiteNumber(String(finding?.signal ?? "").replace("%", ""));
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
          })}
        </div>
      ) : (
        <div className="cc-radar-empty">
          <strong>HAKUNA DATA HALISI YA SENSOR</strong>
          <span>Radar hii haijagundua kifaa chochote. Ukurasa ulioko mtandaoni hauwezi peke yake kusoma Wi-Fi, Bluetooth au simu zilizo karibu.</span>
          <small>Unganisha Device Bridge kwenye PC yako kupitia sehemu ya Device Lab, kisha rudia scan.</small>
          {onOpenDevice && <button type="button" className="cc-inline-button" onClick={onOpenDevice}>FUNGUA DEVICE LAB →</button>}
        </div>
      )}

      <div className="cc-radar-note">CONTACT POSITIONS ARE SCHEMATIC ONLY. BEARING OR DISTANCE IS NOT CLAIMED UNLESS A SENSOR PROVIDES IT.</div>
      </details>
    </div>
  );
}

function WebResearch({ available = false }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState(available ? "IKO TAYARI" : "HAIJAUNGANISHWA");
  const [results, setResults] = useState([]);
  const [message, setMessage] = useState(
    available ? "" : "Utafutaji wa mtandao haujaunganishwa. Tafuta kazi kupitia Job Research, au washa search provider kwenye Settings."
  );

  useEffect(() => {
    setStatus(available ? "IKO TAYARI" : "HAIJAUNGANISHWA");
    setMessage(
      available ? "" : "Utafutaji wa mtandao haujaunganishwa. Tafuta kazi kupitia Job Research, au washa search provider kwenye Settings."
    );
    if (!available) setResults([]);
  }, [available]);

  async function runSearch(event) {
    event?.preventDefault();
    const value = query.trim();
    if (!value) return;
    if (!available) {
      setStatus("HAIJAUNGANISHWA");
      setMessage("Web Research haipatikani mpaka search provider iunganishwe. Mfumo haujatengeneza matokeo ya kubuni.");
      return;
    }

    setStatus("INATAFUTA...");
    setMessage("");
    setResults([]);
    try {
      const data = await searchToolWeb(value);
      const found = Array.isArray(data?.results) ? data.results.slice(0, 4) : [];
      setResults(found);
      setStatus(String(data?.status || "HAIJULIKANI").toUpperCase().replaceAll("_", " "));
      setMessage(data?.message || (found.length ? "" : "Hakuna matokeo yaliyothibitishwa kwa utafutaji huu."));
    } catch (error) {
      setResults([]);
      setStatus("KUNA HITILAFU");
      setMessage(error?.message || "Utafutaji umeshindikana.");
    }
  }

  return (
    <div className="cc-research">
      <form className="cc-research-search" onSubmit={runSearch}>
        <input
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Tafuta mtandaoni..."
          aria-label="Utafutaji wa mtandao"
        />
        <button type="submit" aria-label="Tafuta">›</button>
      </form>
      <div className="cc-research-status">{status}</div>
      {results.length > 0 ? results.map((result, index) => (
        <article className="cc-research-item" key={result.url || index}>
          <span className="cc-research-icon">◎</span>
          <div>
            <a href={result.url} target="_blank" rel="noreferrer"><strong>{result.title || result.url}</strong></a>
            <small>{result.content || result.engine || "Chanzo cha mtandao"}</small>
          </div>
        </article>
      )) : (
        <div className="cc-research-empty">
          {message || (available ? "Andika swali ili kutafuta taarifa zilizopo." : "Mtoa huduma wa utafutaji hajaunganishwa.")}
        </div>
      )}
    </div>
  );
}

function QuickCommands({ system = null }) {
  const services = system?.services || {};
  const aiConfigured = services.ai_core === "CONFIGURED";
  const webConfigured = services.web_search === "CONFIGURED";
  const securityConfigured = services.security === "CONFIGURED";
  const commands = [
    { icon: "⌕", label: "SCAN SYSTEM", kind: "dispatch", command: "scan my system status" },
    ...(aiConfigured ? [
      { icon: "◫", label: "ANALYZE DATA", kind: "ai", prompt: "Analyze the verified MR AI backend runtime telemetry below. Give concise observations and explicitly distinguish the Render backend host from the owner's personal PC. Do not claim any configuration changed." },
    ] : []),
    ...(webConfigured ? [
      { icon: "◎", label: "WEB RESEARCH", kind: "search", query: "latest technology trends in AI and automation" },
    ] : []),
    ...(aiConfigured ? [
      { icon: "▣", label: "GENERATE REPORT", kind: "ai", prompt: "Generate a concise executive report for BOSS FERISI using only the runtime telemetry and service status provided. Include confirmed facts, unknowns, and next actions. Do not invent results." },
    ] : []),
    ...(securityConfigured ? [
      { icon: "◈", label: "SECURITY CHECK", kind: "dispatch", command: "run a security audit check" },
    ] : []),
    ...(aiConfigured ? [
      { icon: "⚙", label: "OPTIMIZE", kind: "ai", prompt: "Review the verified MR AI backend telemetry and service state. Recommend up to three safe, specific optimizations. Do not claim to execute changes." },
    ] : []),
  ];
  const [state, setState] = useState("READY");
  const [busy, setBusy] = useState("");
  const [resultText, setResultText] = useState("");

  async function run(command) {
    if (busy) return;
    setBusy(command.label);
    setState(`RUNNING · ${command.label}`);
    setResultText("");
    try {
      const runtimeContext = {
        source: "MR_AI_DASHBOARD_RUNTIME",
        telemetry: system?.telemetry || {},
        services: system?.services || {},
        ai: system?.ai || {},
      };
      let result;
      if (command.kind === "dispatch") {
        result = await dispatchTool(command.command);
      } else if (command.kind === "search") {
        result = await searchToolWeb(command.query);
      } else {
        result = await chat(command.prompt + "\n\nVERIFIED RUNTIME DATA:\n" + JSON.stringify(runtimeContext), "openrouter", {
          status: "RUNTIME_CONTEXT",
          result: runtimeContext,
        });
      }

      const status = String(result?.status || (result?.response ? "COMPLETED" : "RESPONSE RECEIVED")).toUpperCase();
      setState(`${command.label} · ${status}`);

      if (result?.response) {
        setResultText(result.response);
      } else if (result?.result?.telemetry) {
        const t = result.result.telemetry;
        setResultText([
          "Backend host telemetry snapshot (not personal PC metrics):",
          `CPU: ${finiteNumber(t.cpu_percent) === null ? "N/A" : t.cpu_percent + "%"}`,
          `Memory: ${finiteNumber(t.memory_percent) === null ? "N/A" : t.memory_percent + "%"}`,
          `Storage: ${finiteNumber(t.storage_percent) === null ? "N/A" : t.storage_percent + "%"}`,
          `GPU: ${finiteNumber(t.gpu?.utilization_percent) === null ? "N/A" : t.gpu.utilization_percent + "%"}`,
          `Database: ${result.result.services?.database || "UNKNOWN"}`,
          `AI Core: ${result.result.services?.ai_core || "UNKNOWN"}`,
        ].join("\n"));
      } else if (Array.isArray(result?.results)) {
        setResultText(result.results.length
          ? result.results.slice(0, 4).map((item, index) => `${index + 1}. ${item.title || item.url || "Untitled source"}\n${item.url || ""}`).join("\n\n")
          : result.message || "No verified web results were returned.");
      } else if (result?.message) {
        setResultText(result.message);
      } else if (result?.route?.tool) {
        setResultText(`Tool selected: ${result.route.tool}. Status: ${status}. ${result.message || "Review the connected hand status before assuming the action ran."}`);
      } else {
        setResultText(JSON.stringify(result, null, 2).slice(0, 1800));
      }
    } catch (error) {
      setState(`${command.label} · ERROR`);
      setResultText(error?.message || "Command failed.");
    } finally {
      setBusy("");
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
          <button type="button" key={command.label} onClick={() => run(command)} disabled={Boolean(busy)}>
            <span>{command.icon}</span><strong>{command.label}</strong>
          </button>
        ))}
        
      </div>
      {resultText && <div className="cc-quick-result" role="status" aria-live="polite"><strong>COMMAND OUTPUT</strong><pre>{resultText}</pre></div>}
    </section>
  );
}

function statusLabel(value) {
  const key = String(value || "READY").toUpperCase();
  const labels = {
    READY: "TAYARI",
    PLANNED: "IMEPANGIWA",
    PENDING: "INASUBIRI KUANZA",
    STARTING: "INAANZA",
    RUNNING: "INAENDELEA",
    IN_PROGRESS: "INAENDELEA",
    WORKING: "INAFANYA KAZI",
    EXECUTING: "INAENDESHA",
    COMPLETED: "IMEKAMILIKA",
    WAITING: "INASUBIRI",
    WAITING_FOR_HAND: "INASUBIRI MUUNGANISHO",
    WAITING_FOR_VERIFICATION: "INASUBIRI UTHIBITISHO",
    WAITING_APPROVAL: "INASUBIRI IDHINI",
    NOT_CONNECTED: "HAIJAUNGANISHWA",
    FAILED: "IMESHINDWA",
    ERROR: "KUNA HITILAFU",
    NO_ACTIVE_MISSION: "HAKUNA KAZI INAYOENDELEA",
  };
  return labels[key] || key.replaceAll("_", " ").replaceAll("-", " ");
}

function isTaskActive(task) {
  return !["COMPLETED", "FAILED", "CANCELLED"].includes(String(task?.status || "").toUpperCase());
}


function agentRuntimeLabel(value) {
  const key = String(value || "STANDBY").toUpperCase();
  const labels = {
    STANDBY: "WANASUBIRI KAZI",
    PLANNED: "IMEPANGIWA",
    PENDING: "INASUBIRI KUANZA",
    RUNNING: "INAENDELEA",
    IN_PROGRESS: "INAENDELEA",
    WORKING: "INAFANYA KAZI",
    EXECUTING: "INAENDESHA",
    COMPLETED: "IMEKAMILIKA",
    WAITING: "INASUBIRI",
    WAITING_FOR_HAND: "INASUBIRI MUUNGANISHO",
    WAITING_FOR_VERIFICATION: "INASUBIRI UTHIBITISHO",
    NOT_CONNECTED: "HAIJAUNGANISHWA",
    FAILED: "IMESHINDWA",
    ERROR: "KUNA HITILAFU",
  };
  return labels[key] || key.replaceAll("_", " ");
}

function agentDescriptionSwahili(id, fallback) {
  const descriptions = {
    orchestrator: "Hupanga kazi, hugawa hatua na kufuatilia ushahidi wa matokeo.",
    research: "Hutafuta taarifa na kuripoti vyanzo vilivyopatikana.",
    browser: "Hufanya kazi kwenye Chrome iliyounganishwa na kuidhinishwa.",
    gmail: "Hutafuta na kusoma barua baada ya Gmail kuunganishwa.",
    jobs: "Hutafuta nafasi za kazi na kuonyesha viungo vya tangazo.",
    coding: "Hukagua msimbo na kusaidia kutatua hitilafu za mradi.",
    creative: "Husaidia kutengeneza mabango, nembo na michoro.",
    device: "Huchunguza simu na vifaa kupitia Device Bridge ya PC.",
    security: "Hukagua usanidi na usalama kwa ruhusa.",
    memory: "Huhifadhi na kurejesha kumbukumbu zilizoidhinishwa.",
    scheduler: "Hudhibiti kazi zilizowekwa kwenye ratiba.",
  };
  return descriptions[String(id || "").toLowerCase()] || fallback || "Mwakala maalumu wa MR AI.";
}

function AgentFleet({ agents = [], tasks = [], missionSnapshot = null, onOpenAgents, compact = false }) {
  const steps = Array.isArray(missionSnapshot?.steps)
    ? missionSnapshot.steps
    : Array.isArray(missionSnapshot?.plan?.steps)
      ? missionSnapshot.plan.steps
      : [];
  const workingStatuses = ["RUNNING", "IN_PROGRESS", "WORKING", "EXECUTING"];
  const waitingStatuses = ["WAITING", "WAITING_FOR_HAND", "WAITING_FOR_VERIFICATION"];
  const activeTaskCount = tasks.filter(task => workingStatuses.includes(String(task.status || "").toUpperCase())).length;
  const waitingTaskCount = tasks.filter(task => waitingStatuses.includes(String(task.status || "").toUpperCase())).length;
  const waitingCount = waitingTaskCount + steps.filter(step => waitingStatuses.includes(String(step.status || "").toUpperCase())).length;
  function assignmentFor(agent) {
    const id = String(agent.id || "").toLowerCase().trim();
    const name = String(agent.name || "").toLowerCase().trim();
    return tasks.filter(task => {
      const owner = String(task.agent || "").toLowerCase().trim();
      return owner === id || owner === name || owner.replaceAll(" ", "_") === id;
    }).sort((a, b) => {
      const aWorking = workingStatuses.includes(String(a.status || "").toUpperCase()) ? 1 : 0;
      const bWorking = workingStatuses.includes(String(b.status || "").toUpperCase()) ? 1 : 0;
      return bWorking - aWorking;
    })[0] || null;
  }

  function priorityFor(agent) {
    const id = String(agent.id || "").toLowerCase();
    const task = assignmentFor(agent);
    const taskStatus = String(task?.status || "").toUpperCase();
    const step = [...steps].reverse().find(item => String(item.agent || "").toLowerCase() === id);
    const stepStatus = String(step?.status || "").toUpperCase();
    if (workingStatuses.includes(taskStatus) || ["RUNNING", "IN_PROGRESS", "WORKING", "EXECUTING"].includes(stepStatus)) return 100;
    if (waitingStatuses.includes(taskStatus) || waitingStatuses.includes(stepStatus)) return 80;
    if (step && stepStatus !== "PLANNED") return 70;
    if (task) return 50;
    if (step) return 40;
    return 0;
  }

  const rankedAgents = compact ? [...agents].sort((a, b) => priorityFor(b) - priorityFor(a)) : agents;
  const visibleAgents = compact ? rankedAgents.slice(0, 4) : rankedAgents;

  return (
    <div className="cc-agent-fleet-wrap">
      <div className="cc-agent-fleet-summary">
        <div><span>MAWAKALA WALIOSAJILIWA</span><strong>{agents.length}</strong></div>
        <div><span>WANAFANYA KAZI SASA</span><strong>{activeTaskCount}</strong></div>
        <div><span>KAZI ZILIZOREKODIWA</span><strong>{tasks.length}</strong></div>
        <div><span>ZINAZOSUBIRI MUUNGANISHO</span><strong>{waitingCount}</strong></div>
      </div>
      <div className="cc-agent-fleet-grid">
        {visibleAgents.map(agent => {
          const id = String(agent.id || "").toLowerCase();
          const task = assignmentFor(agent);
          const step = [...steps].reverse().find(item => String(item.agent || "").toLowerCase() === id);
          let rawState = "STANDBY";
          let currentWork = "Hakuna kazi iliyopangiwa kwa sasa";
          if (step) {
            rawState = String(step.status || "PLANNED").toUpperCase();
            currentWork = step.evidence?.message || step.tool || (Array.isArray(step.tools) ? step.tools.slice(0, 2).join(" · ") : "") || "Hatua imepangwa";
          } else if (task) {
            rawState = String(task.status || "PENDING").toUpperCase();
            currentWork = task.title || "Kazi iliyopangiwa";
          }
          const statusClass = rawState.toLowerCase().replaceAll("_", "-");
          const glyph = id === "device" ? "⌁" : id === "creative" ? "✦" : id === "research" ? "◎" : id === "security" ? "◈" : id === "orchestrator" ? "MR" : "◆";
          return (
            <article className="cc-agent-tile" key={agent.id}>
              <div className="cc-agent-tile-top">
                <span className="cc-agent-glyph">{glyph}</span>
                <span className={"cc-agent-state state-" + statusClass}>{agentRuntimeLabel(rawState)}</span>
              </div>
              <strong className="cc-agent-name">{agent.name || id}</strong>
              <p>{agentDescriptionSwahili(id, agent.description)}</p>
              <div className="cc-agent-current"><span>KAZI YA SASA</span><strong>{currentWork}</strong></div>
              <div className="cc-agent-capabilities">{(agent.capabilities || []).slice(0, 3).join(" · ")}</div>
            </article>
          );
        })}
      </div>
      {!agents.length && <div className="cc-agent-empty">Orodha ya mawakala haikupatikana. Bonyeza REFRESH STATUS na ukague muunganisho wa backend.</div>}
      {compact && agents.length > visibleAgents.length && <p className="cc-agent-legend">Wengine {agents.length - visibleAgents.length} wapo kwenye sehemu ya Agents.</p>}
      <button type="button" className="cc-inline-button cc-agent-open" onClick={onOpenAgents}>FUNGUA USIMAMIZI WA MAWAKALA →</button>
      <p className="cc-agent-legend">WANASUBIRI KAZI = wamesajiliwa tu. WAKO KAZINI = kuna kazi hai iliyoripotiwa. MUUNGANISHO UNAOHITAJIKA = kifaa au huduma bado haijaunganishwa.</p>
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
    let latest = null;
    try {
      let finalResult = await executeMission(value);
      latest = finalResult;
      const handoffStep = finalResult?.steps?.find(
        step => step?.status === "WAITING_FOR_HAND" && step?.handoff?.action
      );

      if (handoffStep && finalResult?.mission?.id) {
        setMissionResult({ ...finalResult, status: "HAND_EXECUTING" });
        const action = handoffStep.handoff.action;
        const payload = handoffStep.handoff.payload || {};
        let evidence;

        switch (action) {
          case "NAVIGATE":
            evidence = await browserNavigate(payload.url);
            break;
          case "GET_PAGE_DATA":
            evidence = await getCurrentPage();
            break;
          case "CLICK":
            evidence = await browserClick(payload.selector);
            break;
          case "TYPE":
            evidence = await browserType(payload.selector, payload.value);
            break;
          case "SCROLL":
            evidence = await browserScroll(Number(payload.amount || 700));
            break;
          case "DRAG":
            evidence = await browserDrag(payload.selector, Number(payload.dx || 0), Number(payload.dy || 0));
            break;
          default:
            throw new Error("Kitendo cha browser hakitumiki: " + action);
        }

        const verified = await reportMissionHandoff(finalResult.mission.id, "COMPLETED", {
          agent: handoffStep.agent,
          tool: "browser_hands",
          action,
          result: evidence,
        });
        finalResult = {
          ...finalResult,
          status: verified.status,
          mission: {
            ...finalResult.mission,
            status: verified.mission.status,
            progress: verified.mission.progress,
            result: verified.mission.result,
          },
          next_action: verified.next_action || finalResult.next_action,
          steps: finalResult.steps.map(step => step.step === handoffStep.step
            ? { ...step, status: verified.verified === true ? "COMPLETED" : verified.status, verified: verified.verified === true, evidence: { message: "Browser imerudisha matokeo. Hali ya mwisho inahitaji uthibitisho huru.", result: evidence } }
            : step),
        };
      }

      setMissionResult(finalResult);
      if (finalResult?.plan) setPlanResult(finalResult.plan);
      onMissionUpdate?.(finalResult);
    } catch (err) {
      const reason = err?.message || "Kazi haikuweza kuanza.";
      if (latest?.mission) {
        setMissionResult({
          ...latest,
          status: "WAITING",
          next_action: "Kazi imesimama kwa sababu muunganisho unaohitajika haujapatikana: " + reason,
        });
        onMissionUpdate?.(latest);
      } else {
        setError(reason);
      }
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
        <label htmlFor="cc-mission-request">KAZI / LENGO LA BOSS FERISI</label>
        <input
          id="cc-mission-request"
          value={request}
          onChange={event => setRequest(event.target.value)}
          placeholder="Andika kazi, mfano: tafuta ajira za remote za Python..."
          maxLength={1000}
          required
        />
        <div className="cc-mission-actions">
          <button type="submit" disabled={Boolean(busy) || !request.trim()}>{busy === "PLAN" ? "INAPANGA..." : "PANGA KAZI"}</button>
          <button type="button" className="primary-button" disabled={Boolean(busy) || !request.trim()} onClick={runMission}>{busy === "RUN" ? "INAENDESHA..." : "ANZA KAZI"}</button>
        </div>
      </form>
      <div className="cc-mission-examples">
        <span>ANZA HAPA</span>
        {examples.map(example => <button type="button" key={example} onClick={() => setRequest(example)}>{example}</button>)}
      </div>
      {error && <div className="cc-workbench-error" role="alert">{error}</div>}
      {current ? (
        <div className="cc-mission-result" aria-live="polite">
          <div className="cc-mission-result-head">
            <div><span>HALI YA KAZI</span><strong>{statusLabel(missionResult?.status || planResult?.status || "PLANNED")}</strong></div>
            {missionResult?.mission?.id && <div><span>ID YA KAZI</span><strong>#{missionResult.mission.id}</strong></div>}
            {missionResult?.mission?.progress !== undefined && <div><span>MAENDELEO</span><strong>{missionResult.mission.progress}%</strong></div>}
          </div>
          {steps.length ? (
            <div className="cc-mission-steps">
              {steps.map((step, index) => {
                const evidence = step.evidence || {};
                const jobs = Array.isArray(evidence.results) ? evidence.results.slice(0, 5) : [];
                const rawStatus = String(step.status || "PLANNED").toLowerCase().replaceAll("_", "-");
                const displayName = step.name || ({
                  orchestrator: "MR AI Orchestrator",
                  jobs: "Mtafutaji wa Ajira",
                  research: "Mtafiti",
                  browser: "Msimamizi wa Kivinjari",
                  gmail: "Msimamizi wa Barua Pepe",
                  device: "Mtaalamu wa Vifaa",
                  coding: "Mhandisi wa Msimbo",
                  memory: "Msimamizi wa Kumbukumbu",
                  scheduler: "Msimamizi wa Ratiba",
                }[String(step.agent || "").toLowerCase()] || step.agent || "Wakala");
                return (
                  <div className="cc-mission-step" key={step.step || (step.agent + "-" + index)}>
                    <span className="cc-step-number">{String(step.step || index + 1).padStart(2, "0")}</span>
                    <div className="cc-mission-step-main">
                      <strong>{displayName}</strong>
                      <small>{step.tool || (Array.isArray(step.tools) ? step.tools.slice(0, 3).join(" · ") : "") || (Array.isArray(step.capabilities) ? step.capabilities.slice(0, 3).join(" · ") : "Inasubiri zana inayohitajika")}</small>
                      {evidence.message && <p className="cc-mission-step-note">{evidence.message}</p>}
                      {jobs.length > 0 && (
                        <div className="cc-mission-job-results">
                          {jobs.map((job, jobIndex) => (
                            <a href={job.url} key={job.url || jobIndex} target="_blank" rel="noreferrer">
                              <strong>{job.title || "Nafasi ya kazi"}</strong>
                              <span>{job.company || "Mwajiri hajatambuliwa"} · {job.location || "Eneo halijawekwa"} · {job.source || "Chanzo"}</span>
                            </a>
                          ))}
                        </div>
                      )}
                      {evidence.note && <small className="cc-mission-step-note">{evidence.note}</small>}
                    </div>
                    <span className={"cc-agent-state state-" + rawStatus}>{statusLabel(step.status)}</span>
                  </div>
                );
              })}
            </div>
          ) : <p className="cc-agent-empty">Plan returned no specialist steps.</p>}
          {missionResult?.next_action && <div className="cc-next-action"><strong>HATUA INAYOFUATA</strong><span>{missionResult.next_action}</span></div>}
        </div>
      ) : (
        <div className="cc-workbench-empty"><strong>WAITING FOR YOUR MISSION</strong><span>Agent plan and run evidence will appear here. Nothing runs until you press a mission button.</span></div>
      )}
    </div>
  );
}

function OwnerRequirements({ system, agents = [], tasks = [], memories = [], radarFindings = [], gmailStatus = null, missionSnapshot = null }) {
  const services = system?.services || {};
  const activeTasks = tasks.filter(isTaskActive).length;
  const configuredProviders = ["openrouter", "mistral", "grok", "gemini", "kimi"].filter(
    provider => String(services[provider] || "").toUpperCase() === "CONFIGURED"
  );
  const gmail = String(gmailStatus?.status || services.gmail || "NOT_CONFIGURED").toUpperCase();
  const browser = String(services.extension || "NOT_CONNECTED").toUpperCase();
  const missionSteps = Array.isArray(missionSnapshot?.steps) ? missionSnapshot.steps : [];
  const items = [
    { icon: "◉", title: "Personal command center", state: "READY", detail: "MR AI STAN · BOSS FERISI · MOG343" },
    { icon: "⏻", title: "Normal / Working / Sleep", state: "READY", detail: "Modes are available; always-on wake-word support depends on browser and hardware." },
    { icon: "◆", title: "Agent crew", state: `${activeTasks} ACTIVE TASKS · ${agents.length} REGISTERED`, detail: activeTasks ? "Task-backed assignments are visible above." : "Agents are registered, but no active task is currently assigned." },
    { icon: "⌖", title: "Sensor radar", state: radarFindings.length ? `${radarFindings.length} CONTACTS` : "NO SENSOR DATA", detail: "Local Wi-Fi/Bluetooth/ADB/Fastboot scan needs the PC Device Bridge. No contacts or range are fabricated." },
    { icon: "⌖", title: "Live 2D map", state: "READY", detail: "OpenStreetMap road layer; Street View opens separately where available." },
    { icon: "↗", title: "Browser Hands", state: browser, detail: browser === "CONNECTED" ? "Browser extension reports connected." : "Install/reload the MR AI browser extension and verify its connection before running web actions." },
    { icon: "⌁", title: "Device Lab", state: radarFindings.length ? "SENSOR RESULTS RECEIVED" : "LOCAL BRIDGE NOT VERIFIED", detail: "USB, Android, Fastboot and nearby-radio tools require the local device bridge." },
    { icon: "✉", title: "Gmail", state: gmail, detail: "Gmail tools remain unavailable until OAuth credentials and authorization are configured." },
    { icon: "✦", title: "AI providers", state: configuredProviders.length ? `${configuredProviders.length} KEYS CONFIGURED` : "NO KEYS CONFIGURED", detail: `${configuredProviders.join(", ") || "No configured providers"} · key presence does not prove the API call works; Chat selects one provider per request.` },
    { icon: "✓", title: "Tasks & memory", state: `${tasks.length} TASKS · ${memories.length} MEMORIES`, detail: "Counts reflect records returned for this signed-in account." },
    { icon: "🎙", title: "Voice control", state: "MIC PERMISSION REQUIRED", detail: "Browser voice input requires microphone permission. Always-listening 'amka' or clap wake is not verified by this web session." },
    { icon: "▣", title: "PC + phone", state: "WEB UI AVAILABLE", detail: "The dashboard is web-based; local PC sensors and native device actions require their linked hands." },
  ];

  function tone(state) {
    const value = String(state).toUpperCase();
    if (/NOT_CONNECTED|NOT_CONFIGURED|NO SENSOR|NOT VERIFIED|REQUIRED|NO KEYS/.test(value)) return "warn";
    if (/READY|CONNECTED|SENSOR RESULTS/.test(value)) return "good";
    return "neutral";
  }

  return (
    <div className="cc-owner-board">
      <div className="cc-owner-board-intro">
        <p>Hapa ndipo mahitaji ya MR AI yako yanaonekana pamoja na hali ya sasa. STATUS za configured hazimaanishi kuwa integration imejaribiwa au kwamba agent inafanya kazi yenyewe.</p>
      </div>
      <div className="cc-owner-board-grid">
        {items.map(item => (
          <article className="cc-owner-capability" key={item.title}>
            <div className="cc-owner-capability-head"><span>{item.icon}</span><strong>{item.title}</strong></div>
            <span className={`cc-owner-state tone-${tone(item.state)}`}>{item.state}</span>
            <p>{item.detail}</p>
          </article>
        ))}
      </div>
      {missionSteps.length > 0 && <p className="cc-owner-board-foot">Current plan/mission has {missionSteps.length} steps. Details and handoff status are shown in Mission Workbench.</p>}
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


function ExecutiveMorningBrief({ system, gmailStatus, tasks = [], onOpenAgents, onOpenTasks, onOpenGmail, onOpenJobs }) {
  const [briefing, setBriefing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadBriefing() {
    setLoading(true);
    try {
      const result = await getExecutiveBriefing();
      setBriefing(result);
      setError("");
    } catch (err) {
      setError(err?.message || "Executive briefing is unavailable.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadBriefing();
    const timer = window.setInterval(loadBriefing, 30000);
    return () => window.clearInterval(timer);
  }, []);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "GOOD MORNING, BOSS" : hour < 17 ? "GOOD AFTERNOON, BOSS" : "GOOD EVENING, BOSS";
  const agentSummary = briefing?.agents || {};
  const taskSummary = briefing?.tasks || {};
  const recent = Array.isArray(briefing?.recent_activity) ? briefing.recent_activity.slice(0, 5) : [];
  const jobTasks = tasks.filter(task => String(task?.agent || "").toLowerCase() === "jobs");
  const gmailState = String(gmailStatus?.status || system?.services?.gmail || "UNKNOWN").replaceAll("_", " ");
  const gmailConnected = gmailStatus?.connected === true;
  const blockers = Array.isArray(briefing?.blockers) ? briefing.blockers : [];

  function briefingSpeechText() {
    const greetingText = hour < 12 ? "Good morning, Boss." : hour < 17 ? "Good afternoon, Boss." : "Good evening, Boss.";
    const agentsText = Number.isFinite(agentSummary.total)
      ? (agentSummary.working || 0) + " agents working out of " + agentSummary.total + " registered."
      : "Agent status is not available yet.";
    const tasksText = Number.isFinite(taskSummary.completed)
      ? taskSummary.completed + " tasks completed, " + (taskSummary.working || 0) + " in progress, " + (taskSummary.waiting || 0) + " waiting, and " + (taskSummary.failed || 0) + " failed."
      : "Task summary is not available yet.";
    const priorityText = briefing?.next_action || "No next action has been reported.";
    const gmailText = gmailConnected ? "Gmail is connected, but message and reply totals have not been verified in this briefing." : "Gmail is " + gmailState + ".";
    return [greetingText, "MR AI STAN operational briefing.", agentsText, tasksText, gmailText, "Priority: " + priorityText].join(" ");
  }

  function speakBriefing() {
    if (!("speechSynthesis" in window) || typeof SpeechSynthesisUtterance === "undefined") {
      setError("Voice briefing is not supported by this browser.");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(briefingSpeechText());
    utterance.lang = "en-GB";
    utterance.rate = 0.94;
    utterance.pitch = 0.9;
    window.speechSynthesis.speak(utterance);
  }

  useEffect(() => {
    if (!briefing || !("speechSynthesis" in window) || typeof SpeechSynthesisUtterance === "undefined") return;
    let alreadySpoken = false;
    try { alreadySpoken = sessionStorage.getItem("mr_ai_briefing_spoken") === "1"; } catch {}
    if (alreadySpoken) return;
    try { sessionStorage.setItem("mr_ai_briefing_spoken", "1"); } catch {}
    speakBriefing();
  }, [briefing]);

  function timeLabel(value) {
    if (!value) return "TIME N/A";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "TIME N/A" : date.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  function activityLabel(item) {
    return String(item?.action || "SYSTEM EVENT").replaceAll("_", " ");
  }

  return (
    <section className="cc-executive-brief" aria-labelledby="cc-executive-greeting">
      <div className="cc-executive-hero">
        <div className="cc-executive-copy">
          <span className="cc-eyebrow">MOG343 OPERATIONS // EXECUTIVE BRIEFING</span>
          <h1 id="cc-executive-greeting">{greeting}</h1>
          <p>Muhtasari wa hali ya mfumo, shughuli zilizorekodiwa na hatua zinazohitaji uangalizi.</p>
          <div className="cc-executive-statusline">
            <span className={"cc-exec-pulse " + (briefing ? "is-live" : "is-waiting")} />
            <strong>{loading ? "SYNCING VERIFIED OPERATIONS..." : briefing ? "OPERATIONAL BRIEFING UPDATED" : "BRIEFING NOT AVAILABLE"}</strong>
            <span>{briefing?.generated_at ? timeLabel(briefing.generated_at) : "LIVE DATA PENDING"}</span>
            <button type="button" className="cc-exec-speak" onClick={speakBriefing}>▶ PLAY BRIEFING</button>
          </div>
        </div>
        <div className="cc-executive-orb" aria-hidden="true">
          <div className="cc-exec-orbit cc-exec-orbit-a" />
          <div className="cc-exec-orbit cc-exec-orbit-b" />
          <div className="cc-exec-core">MR<span>AI</span></div>
          <i className="cc-exec-node node-a" /><i className="cc-exec-node node-b" /><i className="cc-exec-node node-c" />
        </div>
      </div>

      <div className="cc-executive-metrics">
        <button type="button" className="cc-exec-metric" onClick={onOpenAgents}>
          <span>AGENT CREW</span><strong>{Number.isFinite(agentSummary.total) ? (agentSummary.working ?? 0) + "/" + agentSummary.total : "N/A"}</strong>
          <small>WORKING NOW</small>
        </button>
        <button type="button" className="cc-exec-metric" onClick={onOpenTasks}>
          <span>TASKS VERIFIED</span><strong>{Number.isFinite(taskSummary.completed) ? taskSummary.completed : "N/A"}</strong>
          <small>{Number.isFinite(taskSummary.total) ? taskSummary.total + " RECORDED TOTAL" : "AWAITING TASK DATA"}</small>
        </button>
        <button type="button" className="cc-exec-metric" onClick={onOpenJobs}>
          <span>JOB WORKFLOW</span><strong>{jobTasks.length}</strong>
          <small>SAVED JOB TASKS · NOT APPLICATIONS SENT</small>
        </button>
        <button type="button" className="cc-exec-metric" onClick={onOpenGmail}>
          <span>GMAIL CHANNEL</span><strong className={gmailConnected ? "exec-good-text" : "exec-warn-text"}>{gmailConnected ? "CONNECTED" : gmailState}</strong>
          <small>{gmailConnected ? "MESSAGE COUNTS NOT PROVIDED BY BRIEFING" : "OPEN TO CONNECT / CHECK ACCESS"}</small>
        </button>
      </div>

      <details className="cc-executive-details">
        <summary>
          <span className="cc-exec-detail-kicker">MORE OPERATIONS</span>
          <span className="cc-exec-detail-copy">Latest activity, priorities and blockers</span>
          <strong>VIEW DETAILS <span aria-hidden="true">＋</span></strong>
        </summary>
        <div className="cc-executive-lower">
        <div className="cc-executive-activity">
          <div className="cc-exec-section-head"><div><span className="cc-eyebrow">AUDIT TRAIL</span><h2>Latest Operations</h2></div><button type="button" onClick={loadBriefing} disabled={loading}>{loading ? "SYNCING..." : "REFRESH ↻"}</button></div>
          {error && <div className="cc-exec-error" role="status">{error}</div>}
          {recent.length ? (
            <div className="cc-exec-activity-list">
              {recent.map((item, index) => (
                <article className="cc-exec-activity-row" key={item.id || index}>
                  <span className="cc-exec-activity-mark">{String(index + 1).padStart(2, "0")}</span>
                  <div><strong>{activityLabel(item)}</strong><p>{item.details || "No additional details were recorded."}</p></div>
                  <time>{timeLabel(item.created_at)}</time>
                </article>
              ))}
            </div>
          ) : <div className="cc-exec-empty">{loading ? "Loading saved activity..." : "No recent activity was returned by the backend."}</div>}
        </div>
        <aside className="cc-executive-priority">
          <span className="cc-eyebrow">CHIEF OF STAFF NOTES</span>
          <h2>Boss, next priorities</h2>
          <p>{briefing?.next_action || "Waiting for a verified briefing from the backend."}</p>
          <div className="cc-exec-priority-stats">
            <div><span>IN PROGRESS</span><strong>{Number.isFinite(taskSummary.working) ? taskSummary.working : "N/A"}</strong></div>
            <div><span>WAITING</span><strong>{Number.isFinite(taskSummary.waiting) ? taskSummary.waiting : "N/A"}</strong></div>
            <div><span>FAILED</span><strong className={taskSummary.failed > 0 ? "exec-warn-text" : ""}>{Number.isFinite(taskSummary.failed) ? taskSummary.failed : "N/A"}</strong></div>
          </div>
          {blockers.length ? (
            <div className="cc-exec-blockers"><strong>NEEDS ATTENTION · {blockers.length}</strong>{blockers.slice(0, 3).map((blocker, index) => <p key={blocker.type || index}>{blocker.message || blocker.type}</p>)}</div>
          ) : briefing ? <div className="cc-exec-clear"><span>✓</span> No blockers were reported in this briefing.</div> : null}
          <div className="cc-exec-shortcuts">
            <button type="button" onClick={onOpenAgents}>AGENT CREW ↗</button>
            <button type="button" onClick={onOpenTasks}>TASKS ↗</button>
            <button type="button" onClick={onOpenGmail}>GMAIL ↗</button>
            <button type="button" onClick={onOpenJobs}>JOB RESEARCH ↗</button>
          </div>
        </aside>
        </div>
        <p className="cc-exec-truth">VERIFIED RECORDS ONLY · Gmail reply totals, sent applications and external link clicks are not inferred unless a connected service returns those records.</p>
      </details>
    </section>
  );
}

export default function DashboardHome({
  system,
  connectionState = "CONNECTING",
  lastRefreshAt = null,
  agents = [],
  radarFindings = [],
  sensorStatus = {},
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
  onOpenTasks,
  onOpenGmail,
  onOpenJobs,
  onRadarScan,
  onOpenDevice,
  clock = null,
}) {
  const telemetry = system?.telemetry || {};
  const services = system?.services || {};
  const uptime = formatUptime(telemetry.uptime_seconds);
  const activeCount = tasks.filter(t => !["COMPLETED", "FAILED"].includes(String(t.status || "").toUpperCase())).length;
  const [missionSnapshot, setMissionSnapshot] = useState(null);

  function handleMissionUpdate(snapshot) {
    setMissionSnapshot(snapshot);
    if (snapshot?.mission) onRefresh?.();
  }

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

      <ExecutiveMorningBrief system={system} gmailStatus={gmailStatus} tasks={tasks} onOpenAgents={onOpenAgents} onOpenTasks={onOpenTasks} onOpenGmail={onOpenGmail} onOpenJobs={onOpenJobs} />

      <div className="cc-top-grid">
        <Panel eyebrow="TELEMETRY YA BACKEND" title="Hali ya Runtime">
          <SystemStatus
            telemetry={telemetry}
            telemetryHistory={telemetryHistory}
            connectionState={connectionState}
            lastRefreshAt={lastRefreshAt}
            onRefresh={onRefresh}
          />
        </Panel>

        <Panel eyebrow="HALI YA AI CORE" title="AI Core" badge={working ? "WORKING MODE" : "NORMAL MODE"}>
          <div className="cc-core-status">
            <div className="cc-core-readout">
              <div><span>AI MODEL</span><strong>{topReadout.model}</strong></div>
              <div><span>AI TIER</span><strong>{topReadout.tier}</strong></div>
              <div><span>AI RUNTIME</span><strong>{system?.ai?.ready ? "LIVE-TESTED" : system?.ai?.configured ? "CONFIGURED · NOT TESTED" : "NOT CONFIGURED"}</strong></div>
              <div><span>UPTIME</span><strong>{topReadout.uptime}</strong></div>
              <div><span>HALI</span><strong>{topReadout.status}</strong></div>
              <div><span>KAZI HAI</span><strong>{topReadout.active}</strong></div>
            </div>
            <HudOrb state={coreState} working={working} />
          </div>
        </Panel>

        <Panel eyebrow="MISSION OVERVIEW" title="Muhtasari wa Kazi">
          <MissionOverview tasks={tasks} />
        </Panel>
      </div>

      <div className="cc-main-grid has-research">
        <Panel eyebrow="RADAR SCAN" title="Radar ya Vifaa" badge={\`${radarFindings.length} CONTACTS\`} className="cc-radar-panel">
          <Radar findings={radarFindings} onRadarScan={onRadarScan} sensorStatus={sensorStatus} onOpenDevice={onOpenDevice} />
        </Panel>

        <Panel eyebrow="LIVE MAP" title="Ramani ya 2D" className="cc-map-panel">
          <LiveMap onOpenMap={onOpenMap} />
        </Panel>

        <Panel eyebrow="MR AI CHAT" title="Mazungumzo na MR AI" className="cc-chat-panel">
          <Chat onState={onState} onModToggle={onModToggle} onPowerCommand={onPowerCommand} />
        </Panel>

        <Panel eyebrow="WEB RESEARCH" title="Utafutaji wa Mtandaoni" className="cc-research-panel">
          <WebResearch available={services.web_search === "CONFIGURED"} />
        </Panel>
      </div>

            <details className="cc-dashboard-drawer cc-mission-drawer">
        <summary>
          <span><strong>MISSION CONTROL</strong><small>Panga kazi na uone matokeo ya mawakala</small></span>
          <b>FUNGUA <span aria-hidden="true">＋</span></b>
        </summary>
        <Panel eyebrow="MISSION CONTROL" title="Wape Mawakala Kazi" badge="MATOKEO YALIYOTHIBITISHWA" className="cc-mission-workbench-panel">
          <MissionWorkbench onMissionUpdate={handleMissionUpdate} />
        </Panel>
      </details>

      <QuickCommands system={system} />


    </div>
  );
}
