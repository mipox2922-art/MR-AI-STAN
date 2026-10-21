import { useCallback, useEffect, useRef, useState } from "react";
import {
  getAgents,
  getStatus,
  getAIState,
  getSystemDiagnostics,
  getAuthStatus,
  getToken,
  clearToken,
  scanRadar,
  scanWifi,
  scanBluetooth,
  getAndroidDevices,
  getFastbootDevices,
  getRadioStatus,
  login,
  register,
  planAgentWork,
  executeMission,
  getTasks,
  getMemories,
  getActivity,
  getGmailStatus,
  reportMissionHandoff,
  getCurrentPage,
  browserNavigate,
  browserClick,
  browserType,
  browserScroll,
  browserDrag,
} from "./api";
import {
  getActiveTaskForAgent,
  getAssignedTaskForAgent,
  getBackendMode,
  getTaskSummary,
  isTaskInProgress,
  isTaskWaiting,
  normalizeMode,
} from "./utils/taskLogic";
import Chat from "./components/Chat";
import CommandBoot from "./components/CommandBoot";
import Core from "./components/Core";
import BrowserHands from "./components/BrowserHands";
import DeviceLab from "./components/DeviceLab";
import CreativeStudio from "./components/CreativeStudio";
import TrackingMap from "./components/TrackingMap";
import SecurityHub from "./components/SecurityHub";
import ToolBox from "./components/ToolBox";
import WebIntelligence from "./components/WebIntelligence";
import CommandPalette from "./components/CommandPalette";
import DashboardHome from "./components/DashboardHome";
import GmailPanel from "./components/GmailPanel";
import SchedulerPanel from "./components/SchedulerPanel";
import JobResearch from "./components/JobResearch";
import TaskCenter from "./components/TaskCenter";
import MemoryCenter from "./components/MemoryCenter";
import VoiceControl from "./components/VoiceControl";

const BUILD_ID = import.meta.env.VITE_BUILD_ID || "MR-AI-STAN";

const NAV = [
  ["dashboard", "⌂", "Dashboard"],
  ["core", "◉", "AI Core"],
  ["agents", "◆", "Agents"],
  ["jobs", "⌕", "Job Research"],
  ["browser", "↗", "Browser Hands"],
  ["device", "⌁", "Device Lab"],
  ["creative", "✦", "Creative Studio"],
  ["map", "⌖", "Tracking Map"],
  ["security", "🛡", "Security"],
  ["tools", "⚙", "Toolbox"],
  ["web", "◎", "Web Intelligence"],
  ["gmail", "✉", "Gmail"],
  ["calendar", "□", "Schedules"],
  ["tasks", "✓", "Tasks"],
  ["memory", "◇", "Memory"],
  ["system", "⌘", "Settings"],
];

function SleepOverlay({ onWake }) {
  return (
    <div className="sleep-overlay" role="dialog" aria-label="MR AI Sleep Mode">
      <div className="sleep-card">
        <div className="sleep-orb">MR</div>
        <span className="eyebrow">MOG343 // MR AI STAN</span>
        <h1>SLEEP MODE</h1>
        <p>Non-essential monitoring and active work are paused. The Command Center is waiting for a wake action.</p>
        <button className="primary-button" onClick={onWake}>WAKE MR AI</button>
      </div>
    </div>
  );
}

function readBrowserDataStatus() {
  if (typeof navigator === "undefined") return { status: "UNKNOWN", type: "NOT AVAILABLE", note: "Browser network API unavailable." };
  const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  const online = navigator.onLine;
  const type = connection?.type || connection?.effectiveType || "TYPE NOT EXPOSED";
  return {
    status: online ? "ONLINE" : "OFFLINE",
    type,
    effective_type: connection?.effectiveType || null,
    note: online
      ? "Browser reports a network link. It does not expose cellular signal strength or prove public internet reachability."
      : "Browser reports offline.",
  };
}

function radarDiagnosticsFrom(result) {
  const incoming = result?.sensor_status || {};
  const counts = result?.counts || {};
  const findings = Array.isArray(result?.findings) ? result.findings : [];
  const countType = type => findings.filter(item => item?.type === type).length;
  return {
    wifi: incoming.wifi || { status: "SCANNED", count: counts.wifi ?? countType("wifi"), source: "RADAR" },
    bluetooth: incoming.bluetooth || { status: "SCANNED", count: counts.bluetooth ?? countType("bluetooth"), source: "RADAR" },
    android: incoming.android || { status: "SCANNED", count: counts.android ?? countType("android"), source: "RADAR" },
    fastboot: incoming.fastboot || { status: "SCANNED", count: counts.fastboot ?? countType("fastboot"), source: "RADAR" },
    radio: incoming.radio || result?.radio || { status: "NOT_CHECKED", note: "No radio hardware status returned." },
    data: readBrowserDataStatus(),
    devices: { status: "SCANNED", count: (counts.android || 0) + (counts.fastboot || 0) },
    last_scan_at: Date.now(),
  };
}

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [setupRequired, setSetupRequired] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let mounted = true;
    getAuthStatus()
      .then(status => {
        if (mounted && status?.setup_required) {
          setSetupRequired(true);
          setMode("register");
        }
      })
      .catch(() => {
        // Login remains available when the optional setup check is unavailable.
      });
    return () => {
      mounted = false;
    };
  }, []);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result =
        mode === "login"
          ? await login(username.trim(), password)
          : await register(username.trim(), password);
      onAuthenticated(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-screen">
      <section className="auth-card">
        <div className="brand-mark">MR AI</div>
        <div className="eyebrow">DIGITAL CHIEF OF STAFF</div>
        <h1>{mode === "login" ? "Command access" : setupRequired ? "Initialize operator" : "Create operator"}</h1>
        <p>{setupRequired ? "First-run setup. Create the operator account that owns this Command Center." : "Secure session. Real tools. Verified actions only."}</p>
        <small className="auth-build-id">BUILD {BUILD_ID}</small>

        <form onSubmit={submit}>
          <label>
            Username
            <input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" required />
          </label>

          <label>
            Password
            <input value={password} onChange={e => setPassword(e.target.value)} type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required />
          </label>

          {error && <div className="auth-error">{error}</div>}

          <button className="primary-button" disabled={busy}>
            {busy ? "CONNECTING..." : mode === "login" ? "ENTER COMMAND CENTER" : "CREATE & ENTER"}
          </button>
        </form>

        <button className="link-button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
          {mode === "login" ? "Create a new operator account" : "Back to login"}
        </button>
      </section>
    </main>
  );
}


function agentDisplayName(id) {
  const names = {
    orchestrator: "MR AI Orchestrator",
    research: "Mtafiti",
    browser: "Msimamizi wa Kivinjari",
    gmail: "Msimamizi wa Barua Pepe",
    jobs: "Mtafutaji wa Ajira",
    coding: "Mhandisi wa Msimbo",
    creative: "Mbunifu",
    device: "Mtaalamu wa Vifaa",
    security: "Mtaalamu wa Usalama",
    memory: "Msimamizi wa Kumbukumbu",
    scheduler: "Msimamizi wa Ratiba",
  };
  const value = String(id || "");
  return names[value.toLowerCase()] || value.replaceAll("_", " ");
}

function agentStatusText(value, kind = "mission") {
  const status = String(value || "").toUpperCase();
  const labels = {
    PLANNED: kind === "plan" ? "IMEPANGWA, BADO HAJAANZA" : "IMEPANGWA",
    PENDING: "INASUBIRI KUANZA",
    STARTING: "INAANZA",
    RUNNING: "INAENDELEA",
    IN_PROGRESS: "INAENDELEA",
    WORKING: "INAFANYA KAZI",
    COMPLETED: "IMEKAMILIKA",
    WAITING: "INASUBIRI MUUNGANISHO",
    WAITING_FOR_HAND: "INASUBIRI MUUNGANISHO",
    WAITING_FOR_VERIFICATION: "INASUBIRI UTHIBITISHO",
    NOT_CONNECTED: "HAIJAUNGANISHWA",
    FAILED: "IMESHINDWA",
    ERROR: "KUNA HITILAFU",
    REJECTED: "IMEKATALIWA",
    HAND_EXECUTING: "INAENDESHA KIVINJARI",
  };
  return labels[status] || status.replaceAll("_", " ") || "HAIJULIKANI";
}

function AgentResultView({ result, kind }) {
  if (!result) return null;
  const steps = Array.isArray(result.steps) ? result.steps : [];
  const mission = result.mission || {};
  const status = mission.status || result.status || (kind === "plan" ? "PLANNED" : "UNKNOWN");
  const agents = Array.isArray(result.agents) && result.agents.length
    ? result.agents
    : [...new Set(steps.map(step => agentDisplayName(step.name || step.agent)).filter(Boolean))];
  const completed = steps.filter(step => String(step.status || "").toUpperCase() === "COMPLETED").length;
  const waiting = steps.filter(step => String(step.status || "").toUpperCase().includes("WAITING")).length;
  const progress = Number.isFinite(Number(mission.progress)) ? Math.max(0, Math.min(100, Number(mission.progress))) : null;

  return (
    <section className={"agent-result " + (kind === "plan" ? "agent-result-plan" : "agent-result-run")} aria-live="polite">
      <div className="agent-result-summary">
        <div><span>HALI</span><strong>{agentStatusText(status, kind)}</strong></div>
        {mission.id != null && <div><span>ID YA KAZI</span><strong>#{mission.id}</strong></div>}
        {progress !== null && <div><span>MAENDELEO</span><strong>{progress}%</strong></div>}
        {kind === "mission" && steps.length > 0 && <div><span>HATUA</span><strong>{completed}/{steps.length} zimekamilika · {waiting} zinasubiri</strong></div>}
      </div>
      {agents.length > 0 && (
        <div className="agent-result-roster">
          <span>MAWAKALA WALIOCHAGULIWA</span>
          <strong>{agents.map(agentDisplayName).join(" · ")}</strong>
        </div>
      )}
      {progress !== null && (
        <div className="agent-result-progress"><i style={{ width: progress + "%" }} /></div>
      )}
      {result.reason && <p className="agent-result-note">{result.reason}</p>}
      {steps.length > 0 && (
        <div className="agent-result-steps">
          {steps.map((step, index) => {
            const stepStatus = String(step.status || "PLANNED").toUpperCase();
            const details = step.evidence?.message || step.evidence?.note || step.message || step.reason || "";
            const jobResults = Array.isArray(step.evidence?.results) ? step.evidence.results.slice(0, 5) : [];
            const tool = step.tool || (Array.isArray(step.tools) ? step.tools.slice(0, 2).join(" · ") : "");
            return (
              <article className={"agent-result-step state-" + stepStatus.toLowerCase().replaceAll("_", "-")} key={step.step || (step.agent + "-" + index)}>
                <span className="agent-result-step-number">{String(step.step || index + 1).padStart(2, "0")}</span>
                <div className="agent-result-step-copy">
                  <strong>{agentDisplayName(step.name || step.agent || "Agent")}</strong>
                  {tool && <small>{tool}</small>}
                  {details && <p>{details}</p>}
                  {jobResults.length > 0 && (
                    <div className="agent-result-jobs">
                      {jobResults.map((job, jobIndex) => (
                        <a href={job.url} key={job.url || jobIndex} target="_blank" rel="noreferrer">
                          <strong>{job.title || "Nafasi ya kazi"}</strong>
                          <span>{job.company || "Mwajiri hajatambuliwa"} · {job.location || "Eneo halijawekwa"} · {job.source || "Chanzo"}</span>
                        </a>
                      ))}
                    </div>
                  )}
                </div>
                <span className="agent-result-step-state">{agentStatusText(stepStatus, kind)}</span>
              </article>
            );
          })}
        </div>
      )}
      {result.next_action && <p className="agent-result-next"><strong>HATUA INAYOFUATA:</strong> {result.next_action}</p>}
      {result.message && !steps.length && <p className="agent-result-note">{result.message}</p>}
      {kind === "plan" && <p className="agent-result-disclaimer">Huu ni mpango tu. Wakala huanza kutekeleza kazi baada ya kuendesha mission.</p>}
    </section>
  );
}

function agentSwahiliDescription(id, fallback) {
  const descriptions = {
    orchestrator: "Hupanga kazi, hugawa hatua na kufuatilia matokeo yaliyothibitishwa.",
    research: "Hutafuta taarifa na kueleza vyanzo vinavyopatikana.",
    browser: "Hufanya kazi kwenye kivinjari kilichounganishwa na kuruhusiwa.",
    gmail: "Hutafuta na kusoma barua baada ya Gmail kuunganishwa.",
    jobs: "Hutafuta nafasi za kazi na kusaidia maandalizi ya maombi.",
    coding: "Hukagua msimbo, hutafuta hitilafu na kuandaa marekebisho.",
    creative: "Husaidia kutengeneza mabango, nembo na michoro.",
    device: "Huchunguza vifaa vinavyopatikana kupitia Device Bridge.",
    security: "Hukagua usanidi na usalama wa mfumo kwa ruhusa.",
    memory: "Huhifadhi na kurejesha kumbukumbu zilizoidhinishwa.",
    scheduler: "Hudhibiti kazi za ratiba na ukumbusho.",
  };
  return descriptions[String(id || "").toLowerCase()] || fallback || "Mwakala maalumu wa MR AI.";
}

function AgentsPanel({ agents, tasks = [], onPlan }) {
  const [request, setRequest] = useState("");
  const [planResult, setPlanResult] = useState(null);
  const [missionResult, setMissionResult] = useState(null);
  const [busy, setBusy] = useState("");
  const workingTasks = tasks.filter(isTaskInProgress);
  const queuedTasks = tasks.filter(isTaskWaiting);

  async function buildMissionPlan() {
    if (!request.trim() || busy) return;
    setBusy("PLAN");
    try {
      const result = await onPlan(request.trim());
      setPlanResult(result);
      setMissionResult(null);
    } catch (error) {
      setPlanResult({ status: "ERROR", reason: error.message });
    } finally {
      setBusy("");
    }
  }

  async function runMission() {
    if (!request.trim() || busy) return;
    setBusy("RUN");
    setMissionResult({ status: "STARTING" });
    try {
      const result = await executeMission(request.trim());
      let finalResult = result;

      const handoffStep = result?.steps?.find(
        step => step?.status === "WAITING_FOR_HAND" && step?.handoff?.action
      );

      if (handoffStep) {
        setMissionResult({
          ...result,
          status: "HAND_EXECUTING",
          handoff: handoffStep.handoff,
        });

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
            evidence = await browserDrag(
              payload.selector,
              Number(payload.dx || 0),
              Number(payload.dy || 0)
            );
            break;
          default:
            throw new Error(`Unsupported browser handoff action: ${action}`);
        }

        const verified = await reportMissionHandoff(
          result.mission.id,
          "COMPLETED",
          {
            agent: handoffStep.agent,
            tool: "browser_hands",
            action,
            result: evidence,
          }
        );

        finalResult = {
          ...result,
          status: verified.status,
          mission: {
            ...result.mission,
            status: verified.mission.status,
            progress: verified.mission.progress,
            result: verified.mission.result,
          },
          next_action: verified.next_action || result.next_action,
          steps: result.steps.map(step =>
            step.step === handoffStep.step
              ? {
                  ...step,
                  status: verified.verified === true ? "COMPLETED" : verified.status,
                  verified: verified.verified === true,
                  evidence,
                }
              : step
          ),
        };
      }

      setMissionResult(finalResult);
    } catch (error) {
      setMissionResult({ status: "ERROR", reason: error.message });
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="panel large-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">USIMAMIZI WA MAWAKALA</span>
          <h2>Mawakala wa MR AI</h2>
        </div>
        <span className="badge">{agents.length} MAWAKALA · {workingTasks.length} KAZINI · {queuedTasks.length} ZINASUBIRI</span>
      </div>

      <p className="agent-panel-intro">Hawa ni wataalamu waliosajiliwa. Hali ya KAZINI huonekana tu kazi inapoendelea kweli; kuwepo kwenye orodha hakumaanishi wakala anafanya kazi.</p>
      <div className="agent-grid">
        {agents.map(agent => {
          const activeTask = getActiveTaskForAgent(agent, tasks);
          const task = activeTask || getAssignedTaskForAgent(agent, tasks);
          const state = activeTask ? "INAENDELEA" : "WANASUBIRI KAZI";
          return (
            <article className="agent-card" key={agent.id}>
              <div className="agent-icon">{agent.id === "device" ? "⌁" : agent.id === "creative" ? "✦" : agent.id === "research" ? "◎" : agent.id === "security" ? "◈" : agent.id === "orchestrator" ? "MR" : "◆"}</div>
              <div className="agent-card-copy">
                <div className="agent-card-heading"><strong>{agentDisplayName(agent.id)}</strong><span className={"agent-result-step-state " + (activeTask ? "agent-working" : "agent-idle")}>{state}</span></div>
                <span>{agentSwahiliDescription(agent.id, agent.description)}</span>
                {task && <small className="agent-card-assignment">KAZI: {task.title || "Kazi isiyo na jina"} · {agentStatusText(task.status)}</small>}
                <small>{agent.risk === "HIGH" ? "HATARI KUBWA" : agent.risk === "MEDIUM" ? "HATARI YA KATI" : "HATARI NDOGO"} · {(agent.capabilities || []).length} UWEZO</small>
              </div>
            </article>
          );
        })}
      </div>

      <div className="planner agent-planner">
        <div className="panel-title">PANGA NA UENDESHE KAZI</div>
        <form className="agent-planner-form" onSubmit={event => { event.preventDefault(); buildMissionPlan(); }}>
          <input value={request} onChange={e => setRequest(e.target.value)} placeholder="Mfano: Kagua afya ya mfumo wa MR AI" disabled={Boolean(busy)} />
          <button type="submit" disabled={Boolean(busy) || !request.trim()}>{busy === "PLAN" ? "INAPANGA..." : "PANGA KAZI"}</button>
          <button type="button" className="primary-button" onClick={runMission} disabled={Boolean(busy) || !request.trim()}>{busy === "RUN" ? "INAENDESHA..." : "ANZA KAZI"}</button>
        </form>
        {planResult && <AgentResultView result={planResult} kind="plan" />}
        {missionResult && <AgentResultView result={missionResult} kind="mission" />}
      </div>
    </section>
  );
}

function App() {
  const [token, setTokenState] = useState(getToken());
  const [active, setActive] = useState("dashboard");
  // One top-level mode state. Backend-reported mode takes precedence when available.
  const [mode, setMode] = useState("normal");
  const [coreState, setCoreState] = useState("IDLE");
  const [system, setSystem] = useState(null);
  const [diagnostics, setDiagnostics] = useState(null);
  const [diagnosticsBusy, setDiagnosticsBusy] = useState(false);
  const [diagnosticsError, setDiagnosticsError] = useState("");
  const [agents, setAgents] = useState([]);
  const [radarFindings, setRadarFindings] = useState([]);
  const [radarDiagnostics, setRadarDiagnostics] = useState(() => ({
    wifi: { status: "NOT_SCANNED" },
    bluetooth: { status: "NOT_SCANNED" },
    android: { status: "NOT_SCANNED" },
    fastboot: { status: "NOT_SCANNED" },
    radio: { status: "NOT_CHECKED" },
    data: readBrowserDataStatus(),
    devices: { status: "NOT_SCANNED", count: 0 },
  }));
  const [tasks, setTasks] = useState([]);
  const [taskListAvailable, setTaskListAvailable] = useState(false);
  const [memories, setMemories] = useState([]);
  const [activities, setActivities] = useState([]);
  const [telemetryHistory, setTelemetryHistory] = useState([]);
  const [gmailStatus, setGmailStatus] = useState(null);
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [clock, setClock] = useState(new Date());
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [bootVisible, setBootVisible] = useState(() => (
    !window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ));
  const finishBoot = useCallback(() => setBootVisible(false), []);
  const [connectionState, setConnectionState] = useState("CONNECTING");
  const [lastRefreshAt, setLastRefreshAt] = useState(null);
  const refreshInFlight = useRef(false);

  const authenticated = Boolean(token);
  const [isMobileViewport, setIsMobileViewport] = useState(() =>
    window.matchMedia("(max-width: 760px)").matches
  );

  useEffect(() => {
    const mediaQuery = window.matchMedia("(max-width: 760px)");
    const syncMobileViewport = () => setIsMobileViewport(mediaQuery.matches);
    syncMobileViewport();
    mediaQuery.addEventListener("change", syncMobileViewport);
    return () => mediaQuery.removeEventListener("change", syncMobileViewport);
  }, []);

  const dashboardRootRef = useRef(null);

  useEffect(() => {
    const root = dashboardRootRef.current;
    if (!root || active !== "dashboard" || !authenticated || isMobileViewport) return undefined;

    const updateCanvasScale = () => {
      const scale = Math.min(window.innerWidth / 1536, window.innerHeight / 1024);
      root.style.setProperty("--dashboard-canvas-scale", String(scale));
    };

    document.body.classList.add("dashboard-canvas-active");
    updateCanvasScale();
    window.addEventListener("resize", updateCanvasScale, { passive: true });
    return () => {
      window.removeEventListener("resize", updateCanvasScale);
      document.body.classList.remove("dashboard-canvas-active");
    };
  }, [active, authenticated, isMobileViewport]);

  const refresh = useCallback(async () => {
    if (!getToken() || refreshInFlight.current || document.visibilityState !== "visible") return;
    refreshInFlight.current = true;
    setConnectionState(current => current === "ONLINE" ? current : "CONNECTING");

    try {
      const results = await Promise.allSettled([
        getStatus(),
        getAgents(),
        getTasks(),
        getMemories(),
        getActivity(),
        getGmailStatus(),
      ]);

      const unauthorized = results.some(
        result => result.status === "rejected" && result.reason?.status === 401
      );

      if (unauthorized) {
        clearToken();
        setTokenState(null);
        return;
      }

      const [statusResult, fleetResult, taskResult, memoryResult, activityResult, gmailResult] = results;

      if (statusResult.status === "fulfilled") {
        const status = statusResult.value;
        setSystem(status);
        const backendMode = getBackendMode(status);
        if (backendMode) {
          setMode(backendMode);
          try { localStorage.setItem("mr_ai_mode", backendMode); } catch {}
          setCoreState(backendMode === "sleep" ? "SLEEPING" : "IDLE");
        }
        setConnectionState("ONLINE");
        setTelemetryHistory(history => [
          ...history,
          { ...(status.telemetry || {}), captured_at: Date.now() }
        ].slice(-24));
      } else {
        setConnectionState("DEGRADED");
      }

      if (fleetResult.status === "fulfilled") {
        const fleet = fleetResult.value;
        setAgents(Array.isArray(fleet) ? fleet : []);
      }
      if (taskResult.status === "fulfilled" && Array.isArray(taskResult.value)) {
        setTasks(taskResult.value);
        setTaskListAvailable(true);
      } else {
        setTasks([]);
        setTaskListAvailable(false);
      }
      if (memoryResult.status === "fulfilled") {
        const memoryRows = memoryResult.value;
        setMemories(Array.isArray(memoryRows) ? memoryRows : []);
      }
      if (activityResult.status === "fulfilled") {
        const activityRows = activityResult.value;
        setActivities(Array.isArray(activityRows) ? activityRows : []);
      }
      if (gmailResult.status === "fulfilled") {
        setGmailStatus(gmailResult.value);
      }

      // Local Wi-Fi/BLE/ADB/Fastboot scans run only after an explicit user action.
      // Do not trigger hardware scans in the recurring telemetry poll.

      setLastRefreshAt(Date.now());
    } catch (error) {
      if (error?.status === 401 || /401|unauthorized/i.test(error?.message || "")) {
        clearToken();
        setTokenState(null);
      } else {
        setConnectionState(current => current === "ONLINE" ? "DEGRADED" : "OFFLINE");
      }
    } finally {
      refreshInFlight.current = false;
    }
  }, []);

  useEffect(() => {
    if (!authenticated) return undefined;
    if (mode !== "sleep" && document.visibilityState === "visible") refresh();
    const timer = mode === "sleep" ? null : setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 7000);
    const clockTimer = setInterval(() => setClock(new Date()), 1000);
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible" && mode !== "sleep") refresh();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    const onShortcut = event => {
      if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "m") {
        event.preventDefault();
        setMode(current => {
          const next = current === "working" ? "normal" : "working";
          localStorage.setItem("mr_ai_mode", next);
          setCoreState(next === "working" ? "WORKING" : "IDLE");
          return next;
        });
      }
    };

    const refreshDataLink = () => setRadarDiagnostics(current => ({ ...current, data: readBrowserDataStatus() }));
    window.addEventListener("online", refreshDataLink);
    window.addEventListener("offline", refreshDataLink);
    const browserConnection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    browserConnection?.addEventListener?.("change", refreshDataLink);

    const onCommandPalette = event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
    };

    window.addEventListener("keydown", onShortcut);
    window.addEventListener("keydown", onCommandPalette);

    return () => {
      if (timer) clearInterval(timer);
      clearInterval(clockTimer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("keydown", onShortcut);
      window.removeEventListener("keydown", onCommandPalette);
      window.removeEventListener("online", refreshDataLink);
      window.removeEventListener("offline", refreshDataLink);
      browserConnection?.removeEventListener?.("change", refreshDataLink);
    };
  }, [authenticated, refresh, mode]);

  useEffect(() => {
    if (!authenticated) return undefined;
    let active = true;
    getAIState()
      .then(result => {
        const state = String(result?.state || "").toUpperCase();
        if (active && ["IDLE", "THINKING", "SPEAKING", "ERROR"].includes(state)) setCoreState(state);
      })
      .catch(() => {
        // The initial IDLE display is not a provider health claim.
      });
    return () => { active = false; };
  }, [authenticated]);

  const telemetry = system?.telemetry || {};
  const services = system?.services || {};

  async function handleRadarScan(source = "all") {
    const normalized = String(source).toLowerCase();
    if (normalized === "all") {
      const result = await scanRadar();
      const findings = Array.isArray(result?.findings) ? result.findings : [];
      setRadarFindings(findings);
      setRadarDiagnostics(radarDiagnosticsFrom(result));
      return result;
    }
    if (normalized === "radio") {
      const result = await getRadioStatus();
      setRadarDiagnostics(current => ({ ...current, radio: result, last_scan_at: Date.now() }));
      return { status: result?.status || "CHECKED", findings: radarFindings, sensor_status: { radio: result }, message: result?.note || "RF hardware checked; no spectrum sweep claimed." };
    }
    if (normalized === "data") {
      const data = readBrowserDataStatus();
      setRadarDiagnostics(current => ({ ...current, data, last_scan_at: Date.now() }));
      return { status: data.status, findings: radarFindings, sensor_status: { data }, message: data.note };
    }

    let result;
    let type;
    if (normalized === "wifi") { result = await scanWifi(); type = "wifi"; }
    else if (normalized === "bluetooth") { result = await scanBluetooth(); type = "bluetooth"; }
    else if (normalized === "android") { result = await getAndroidDevices(); type = "android"; }
    else if (normalized === "fastboot") { result = await getFastbootDevices(); type = "fastboot"; }
    else throw new Error(`Unknown radar source: ${source}`);

    const nextFindings = type === "wifi"
      ? (Array.isArray(result?.networks) ? result.networks.map(network => ({
          type: "wifi", label: network.ssid || "(hidden)",
          signal: network.signal_percent ?? network.bssids?.[0]?.signal ?? null,
          source: result.source || "Wi-Fi",
        })) : [])
      : type === "bluetooth"
        ? (Array.isArray(result?.devices) ? result.devices.map(device => ({
            type: "bluetooth", label: device.name || device.address || "BLE device",
            signal: device.rssi ?? null, distance_estimate_m: device.distance_estimate_m,
            distance_confidence: device.distance_confidence, direction: device.direction || "UNKNOWN", source: "BLE",
          })) : [])
        : (Array.isArray(result?.devices) ? result.devices.map(device => ({
            type, label: device.serial || type.toUpperCase(), signal: null,
            source: type === "android" ? "ADB" : "FASTBOOT",
          })) : []);
    const nextSnapshot = [...radarFindings.filter(item => item?.type !== type), ...nextFindings];
    const sensorState = { status: "SCANNED", count: nextFindings.length, source: result?.source || (type === "bluetooth" ? "LOCAL BLE" : type.toUpperCase()), note: result?.message || "" };
    setRadarFindings(nextSnapshot);
    setRadarDiagnostics(current => ({
      ...current,
      [type]: sensorState,
      devices: type === "android" || type === "fastboot"
        ? { status: "SCANNED", count: nextSnapshot.filter(item => ["android", "fastboot"].includes(item?.type)).length }
        : current.devices,
      last_scan_at: Date.now(),
    }));
    return { status: "SCANNED", findings: nextSnapshot, sensor_status: { [type]: sensorState }, result };
  }

  function authenticate(result) {
    setTokenState(result.access_token);
  }

  function logout() {
    clearToken();
    setTokenState(null);
  }

  async function createPlan(request) {
    return planAgentWork(request);
  }

  async function runSelfCheck() {
    setDiagnosticsBusy(true);
    setDiagnosticsError("");
    try {
      setDiagnostics(await getSystemDiagnostics());
    } catch (error) {
      setDiagnosticsError(error.message || "Self-check failed.");
    } finally {
      setDiagnosticsBusy(false);
    }
  }

  if (!authenticated) {
    return <AuthScreen onAuthenticated={authenticate} />;
  }

  const normalizedMode = normalizeMode(mode) || "normal";
  const working = normalizedMode === "working";
  const sleeping = normalizedMode === "sleep";
  const taskSummary = getTaskSummary(tasks, agents);
  const runtimeCoreState = String(coreState || "IDLE").toUpperCase();
  const coreStatus = sleeping ? "SLEEPING"
    : ["THINKING", "SPEAKING", "ERROR"].includes(runtimeCoreState) ? runtimeCoreState
    : taskSummary.inProgress > 0 ? "WORKING" : "IDLE";

  function setOperationalMode(nextMode) {
    const next = ["normal", "working", "sleep"].includes(nextMode)
      ? nextMode
      : "normal";
    localStorage.setItem("mr_ai_mode", next);
    setMode(next);
    // Mode itself does not imply a real task is running.
    setCoreState(next === "sleep" ? "SLEEPING" : "IDLE");
  }

  function toggleMode(nextWorking) {
    const next =
      typeof nextWorking === "boolean"
        ? nextWorking
        : mode !== "working";
    setOperationalMode(next ? "working" : "normal");
  }

  function handlePowerCommand(command) {
    if (command === "sleep") {
      setOperationalMode("sleep");
      return;
    }
    if (command === "wake") {
      setOperationalMode("normal");
    }
  }

  return (
    <div ref={dashboardRootRef} className={`app-shell ${active === "dashboard" && !isMobileViewport ? "dashboard-canvas-shell" : ""} ${working ? "mode-working" : ""} ${sleeping ? "mode-sleep" : ""}`}>
      <div className="mrai-ambient" aria-hidden="true">
        <svg viewBox="-300 -300 600 600">
          <circle r="290" strokeDasharray="2 8" />
          <g className="mrai-rot"><circle r="260" strokeWidth="6" strokeDasharray="80 30 10 30" /></g>
          <g className="mrai-rot reverse"><circle r="215" strokeWidth="2" strokeDasharray="3 6" /><circle r="200" /></g>
          <g className="mrai-rot"><path d="M-150 0A150 150 0 0 1 0 -150" strokeWidth="10" /><path d="M150 0A150 150 0 0 1 0 150" strokeWidth="10" /></g>
          <polygon points="0,-105 91,-52 91,52 0,105 -91,52 -91,-52" strokeWidth="1.5" />
          <circle r="70" strokeWidth="3" /><circle className="mrai-orb-core" r="40" strokeWidth="2" /><circle className="mrai-orb-dot" r="14" />
        </svg>
      </div>
      <div className="mrai-hud-frame" aria-hidden="true" />
      <div className="mrai-scanlines" aria-hidden="true" />
      {bootVisible && <CommandBoot onFinish={finishBoot} />}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">MR AI</div>
          <div className="brand-sub">STAN // COMMAND CENTER</div>
        </div>

        <div className="operator">
          <Core state={coreStatus} modActive={working} />
          <div>
            <strong>BOSS FERISI</strong>
            <span>OWNER // COMMANDER</span>
            <small>MR AI MANAGER · MOG343 OPERATIONS</small>
          </div>
        </div>

        <nav>
          {NAV.map(([id, icon, label]) => (
            <button className={active === id ? "active" : ""} onClick={() => setActive(id)} key={id}>
              <span>{icon}</span>{label}
            </button>
          ))}
        </nav>

        <div className="sidebar-voice">
          <div className="sidebar-voice-head">
            <span className="eyebrow">WAKE PHRASE</span>
            <span className="voice-state-dot">●</span>
          </div>
          <div className="sidebar-wave" aria-hidden="true">
            {Array.from({ length: 13 }).map((_, index) => <span key={index} />)}
          </div>
          <div className="sidebar-voice-quote">
            <strong>{voiceTranscript ? `"${voiceTranscript}"` : '"Hey Ferisi"'}</strong>
            <span>{voiceTranscript ? "Command received." : "I’m at your service."}</span>
          </div>
          <VoiceControl
            onTranscript={text => {
              setVoiceTranscript(text);
              const command = String(text || "")
                .trim()
                .toLowerCase()
                .replace(/[.!?]+$/g, "")
                .replace(/\s+/g, " ");

              if (["zima", "lala", "sleep", "sleep mode"].includes(command)) {
                handlePowerCommand("sleep");
              } else if (["amka", "wake", "wake up", "amka mr ai"].includes(command)) {
                handlePowerCommand("wake");
              } else if ([
                "vip", "vip mode", "vip kaka", "vip on", "washa vip",
                "mod on", "washa mod", "working mode", "washa working mode"
              ].includes(command)) {
                toggleMode(true);
              } else if ([
                "vip off", "mod off", "zima mod", "normal", "normal mode",
                "washa normal mode"
              ].includes(command)) {
                toggleMode(false);
              }
            }}
          />
        </div>

        <div className="sidebar-footer">
          <button className={working ? "danger-button" : "primary-button"} onClick={() => toggleMode(!working)}>
            {working ? "NORMAL MODE" : "WORKING MODE"}
          </button>
          {!sleeping && (
            <button className="ghost-button" onClick={() => setOperationalMode("sleep")}>
              SLEEP SYSTEM
            </button>
          )}
          <button className="ghost-button" onClick={logout}>DISCONNECT SESSION</button>
        </div>
      </aside>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={setActive}
        onToggleMode={() => toggleMode()}
      />

      {sleeping && <SleepOverlay onWake={() => setOperationalMode("normal")} />}

      <main className={`main-area ${active === "dashboard" ? "dashboard-main" : ""}`}>
        <header className="topbar">
          <div>
            <span className="eyebrow">MOG343 // MR AI STAN</span>
            <h1>{NAV.find(item => item[0] === active)?.[2] || "Command Center"}</h1>
          </div>
          <div className="top-status">
            <div>
              <strong>{clock.toLocaleTimeString("sw-TZ", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</strong>
              <span>{clock.toLocaleDateString("sw-TZ", { weekday: "short", day: "2-digit", month: "short", year: "numeric" })}</span>
            </div>
            <button
              type="button"
              className="mode-indicator"
              onClick={() => toggleMode()}
              aria-label="Toggle NORMAL MODE / WORKING MODE"
              style={{ background: "transparent", border: 0, padding: 0, color: "inherit", font: "inherit", cursor: "pointer" }}
            >
              <span className="mode-label">{sleeping ? "SLEEP MODE" : working ? "WORKING MODE" : "NORMAL MODE"}</span>
              <span className="live-dot">{sleeping ? "PAUSED" : "LIVE"}</span>
            </button>
          </div>
        </header>

        <div className="content">
          {active === "dashboard" && (
            <DashboardHome
              system={system}
              connectionState={connectionState}
              lastRefreshAt={lastRefreshAt}
              telemetryHistory={telemetryHistory}
              gmailStatus={gmailStatus}
              agents={agents}
              radarFindings={radarFindings}
              sensorStatus={radarDiagnostics}
              tasks={tasks}
              tasksAvailable={taskListAvailable}
              memories={memories}
              activities={activities}
              coreState={coreState}
              coreStatus={coreStatus}
              mode={normalizedMode}
              working={working}
              onRefresh={refresh}
              onState={setCoreState}
              onModToggle={toggleMode}
              onPowerCommand={handlePowerCommand}
              onOpenMap={() => setActive("map")}
              onOpenAgents={() => setActive("agents")}
              onOpenTasks={() => setActive("tasks")}
              onOpenGmail={() => setActive("gmail")}
              onOpenJobs={() => setActive("jobs")}
              onOpenDevice={() => setActive("device")}
              onRadarScan={handleRadarScan}
              clock={clock}
            />
          )}

          {active === "core" && (
            <section className="split-grid">
              <div className="panel large-panel core-detail">
                <div className="panel-head">
                  <div>
                    <span className="eyebrow">AI CORE</span>
                    <h2>Operational State Machine</h2>
                  </div>
                </div>
                <div className="state-grid">
                  {["IDLE", "THINKING", "SPEAKING", "WORKING", "ERROR", "SLEEPING"].map(state => (
                    <span aria-current={coreState === state ? "true" : undefined} className={coreState === state ? "state-active" : ""} key={state}>{state}</span>
                  ))}
                </div>
                <div className="core-stage tall"><Core state={coreStatus} modActive={working} /></div>
              </div>
              <Chat
                onState={setCoreState}
                onModToggle={toggleMode}
                onPowerCommand={handlePowerCommand}
                mode={normalizedMode}
                coreStatus={coreStatus}
                tasks={tasks}
                tasksAvailable={taskListAvailable}
                telemetry={system?.telemetry || null}
              />
            </section>
          )}

          {active === "agents" && <AgentsPanel agents={agents} tasks={tasks} onPlan={createPlan} />}
          {active === "jobs" && <JobResearch />}
          {active === "browser" && <BrowserHands />}
          {active === "device" && <DeviceLab />}
          {active === "creative" && <CreativeStudio />}
          {active === "web" && <WebIntelligence />}
          {active === "gmail" && <GmailPanel />}
          {active === "calendar" && <SchedulerPanel />}
          {active === "map" && <TrackingMap />}
          {active === "security" && <SecurityHub />}
          {active === "tools" && <ToolBox />}

          {active === "tasks" && (
            <TaskCenter
              tasks={tasks}
              onOpenAgents={() => setActive("agents")}
            />
          )}

          {active === "memory" && <MemoryCenter />}

          {active === "system" && (
            <section className="panel large-panel">
              <div className="panel-head">
                <div><span className="eyebrow">SYSTEM</span><h2>Verified Service State</h2></div>
                <div className="settings-actions">
                  <button type="button" className="mini-button" onClick={refresh}>REFRESH STATUS</button>
                  <button type="button" className="ghost-button" onClick={() => {
                    const snapshot = {
                      exported_at: new Date().toISOString(),
                      connection_state: connectionState,
                      system,
                      agents: agents.map(({ id, name, risk, capabilities }) => ({ id, name, risk, capabilities })),
                      task_count: tasks.length,
                      memory_count: memories.length,
                      radar_contact_count: radarFindings.length,
                      radar_sensor_status: radarDiagnostics,
                      gmail_status: gmailStatus,
                    };
                    const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" });
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = "mr-ai-runtime-snapshot.json";
                    link.click();
                    URL.revokeObjectURL(url);
                  }}>EXPORT SNAPSHOT</button>
                </div>
              </div>
              <div className="settings-actions" style={{ margin: "12px 0" }}>
                <button type="button" className="primary-button" onClick={runSelfCheck} disabled={diagnosticsBusy}>
                  {diagnosticsBusy ? "CHECKING..." : "RUN SELF-CHECK"}
                </button>
                {diagnostics && <span className="badge">{diagnostics.status} · {diagnostics.checks.length} CHECKS</span>}
              </div>
              {diagnosticsError && <p className="auth-error" role="alert">{diagnosticsError}</p>}
              {diagnostics && (
                <div className="service-grid diagnostics-grid">
                  {diagnostics.checks.map(check => (
                    <div className="service-card" key={check.id}>
                      <span>{check.label}</span>
                      <strong className={String(check.status).toLowerCase().replaceAll("_", "-")}>{check.status}</strong>
                      <small>{check.detail}</small>
                    </div>
                  ))}
                  <p>{diagnostics.truth_boundary}</p>
                </div>
              )}
              <div className="service-grid">
                {Object.entries(services).map(([name, value]) => (
                  <div className="service-card" key={name}>
                    <span>{name.replaceAll("_", " ")}</span>
                    <strong className={String(value).toLowerCase().replaceAll(" ", "-")}>{value}</strong>
                  </div>
                ))}
              </div>
              <pre className="telemetry-json">{JSON.stringify(system, null, 2)}</pre>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
