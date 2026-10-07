import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getAgents,
  getStatus,
  getToken,
  scanRadar,
  login,
  register,
  planAgentWork,
  executeMission,
  getTasks,
  getMemories,
  getActivity,
  reportMissionHandoff,
  getCurrentPage,
  browserNavigate,
  browserClick,
  browserType,
  browserScroll,
  browserDrag,
} from "./api";
import Chat from "./components/Chat";
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
import VoiceControl from "./components/VoiceControl";

const NAV = [
  ["dashboard", "⌂", "Dashboard"],
  ["core", "◉", "AI Core"],
  ["agents", "◆", "Agents"],
  ["browser", "↗", "Browser Hands"],
  ["device", "⌁", "Device Lab"],
  ["creative", "✦", "Creative Studio"],
  ["map", "⌖", "Tracking Map"],
  ["security", "🛡", "Security"],
  ["tools", "⚙", "Toolbox"],
  ["web", "◎", "Web Intelligence"],
  ["gmail", "✉", "Gmail"],
  ["tasks", "✓", "Tasks"],
  ["memory", "◇", "Memory"],
  ["system", "⌘", "System"],
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

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result =
        mode === "login"
          ? await login(username.trim(), password)
          : await register(username.trim(), password, email.trim());
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
        <h1>{mode === "login" ? "Command access" : "Create operator"}</h1>
        <p>Secure session. Real tools. Verified actions only.</p>

        <form onSubmit={submit}>
          <label>
            Username
            <input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" required />
          </label>

          {mode === "register" && (
            <label>
              Email
              <input value={email} onChange={e => setEmail(e.target.value)} type="email" autoComplete="email" required />
            </label>
          )}

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

function AgentsPanel({ agents, onPlan }) {
  const [request, setRequest] = useState("");
  const [planResult, setPlanResult] = useState(null);
  const [missionResult, setMissionResult] = useState(null);

  async function buildMissionPlan() {
    if (!request.trim()) return;
    try {
      const result = await onPlan(request.trim());
      setPlanResult(result);
      setMissionResult(null);
    } catch (error) {
      setPlanResult({ status: "ERROR", reason: error.message });
    }
  }

  async function runMission() {
    if (!request.trim()) return;
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

        if (evidence?.verified === false) {
          throw new Error("Browser handoff returned an unverified result.");
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
          steps: result.steps.map(step =>
            step.step === handoffStep.step
              ? {
                  ...step,
                  status: "COMPLETED",
                  verified: true,
                  evidence,
                }
              : step
          ),
        };
      }

      setMissionResult(finalResult);
    } catch (error) {
      setMissionResult({ status: "ERROR", reason: error.message });
    }
  }

  return (
    <section className="panel large-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">AGENT ORCHESTRATION</span>
          <h2>Specialist Fleet</h2>
        </div>
        <span className="badge">{agents.length} AGENTS</span>
      </div>

      <div className="agent-grid">
        {agents.map(agent => (
          <article className="agent-card" key={agent.id}>
            <div className="agent-icon">{agent.id === "device" ? "⌁" : agent.id === "creative" ? "✦" : "◆"}</div>
            <div>
              <strong>{agent.name}</strong>
              <span>{agent.description}</span>
              <small>{agent.risk} RISK · {agent.capabilities.length} TOOLS</small>
            </div>
          </article>
        ))}
      </div>

      <div className="planner">
        <div className="panel-title">MISSION PLANNER</div>
        <div className="planner-row">
          <input value={request} onChange={e => setRequest(e.target.value)} placeholder="Mfano: nitafutie remote jobs za Python na React" />
          <button onClick={buildMissionPlan}>PLAN</button>
          <button className="primary-button" onClick={runMission}>RUN MISSION</button>
        </div>
        {planResult && (
          <pre className="plan-output">{JSON.stringify(planResult, null, 2)}</pre>
        )}
        {missionResult && (
          <pre className="plan-output mission-output">{JSON.stringify(missionResult, null, 2)}</pre>
        )}
      </div>
    </section>
  );
}

function App() {
  const [token, setTokenState] = useState(getToken());
  const [active, setActive] = useState("dashboard");
  const [mode, setMode] = useState(() => localStorage.getItem("mr_ai_mode") || "normal");
  const [coreState, setCoreState] = useState(() => {
    const saved = localStorage.getItem("mr_ai_mode");
    return saved === "sleep" ? "SLEEPING" : saved === "working" ? "WORKING" : "IDLE";
  });
  const [system, setSystem] = useState(null);
  const [agents, setAgents] = useState([]);
  const [radarFindings, setRadarFindings] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [memories, setMemories] = useState([]);
  const [activities, setActivities] = useState([]);
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [clock, setClock] = useState(new Date());
  const [paletteOpen, setPaletteOpen] = useState(false);

  const authenticated = Boolean(token);

  const refresh = useCallback(async () => {
    if (!getToken()) return;
    try {
      const [status, fleet, taskRows, memoryRows, activityRows] = await Promise.all([
        getStatus(),
        getAgents(),
        getTasks(),
        getMemories(),
        getActivity(),
      ]);
      let radar = [];
      try {
        const result = await scanRadar();
        radar = result.findings || [];
      } catch {
        radar = [];
      }
      setSystem(status);
      setTelemetryHistory(history => [
        ...history,
        { ...(status.telemetry || {}), captured_at: Date.now() }
      ].slice(-24));
      setAgents(fleet);
      setTasks(Array.isArray(taskRows) ? taskRows : []);
      setMemories(Array.isArray(memoryRows) ? memoryRows : []);
      setActivities(Array.isArray(activityRows) ? activityRows : []);
      setRadarFindings(radar);
    } catch (error) {
      if (/401|unauthorized/i.test(error.message)) {
        localStorage.removeItem("mr_ai_token");
        setTokenState(null);
      }
    }
  }, []);

  useEffect(() => {
    if (!authenticated) return undefined;
    if (mode !== "sleep") refresh();
    const timer = mode === "sleep" ? null : setInterval(refresh, 5000);
    const clockTimer = setInterval(() => setClock(new Date()), 1000);

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
      window.removeEventListener("keydown", onShortcut);
      window.removeEventListener("keydown", onCommandPalette);
    };
  }, [authenticated, refresh, mode]);

  const telemetry = system?.telemetry || {};
  const services = system?.services || {};
  const uptime = telemetry.uptime_seconds;
  const uptimeLabel = useMemo(() => {
    if (!Number.isFinite(uptime)) return "N/A";
    const days = Math.floor(uptime / 86400);
    const hours = Math.floor((uptime % 86400) / 3600);
    return days + "d " + String(hours).padStart(2, "0") + "h";
  }, [uptime]);

  function authenticate(result) {
    setTokenState(result.access_token);
  }

  function logout() {
    localStorage.removeItem("mr_ai_token");
    setTokenState(null);
  }

  async function createPlan(request) {
    return planAgentWork(request);
  }

  if (!authenticated) {
    return <AuthScreen onAuthenticated={authenticate} />;
  }

  const working = mode === "working";
  const sleeping = mode === "sleep";

  function setOperationalMode(nextMode) {
    const next = ["normal", "working", "sleep"].includes(nextMode)
      ? nextMode
      : "normal";
    localStorage.setItem("mr_ai_mode", next);
    setMode(next);
    setCoreState(
      next === "sleep"
        ? "SLEEPING"
        : next === "working"
          ? "WORKING"
          : "IDLE"
    );
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
    <div className={`app-shell ${working ? "mode-working" : ""} ${sleeping ? "mode-sleep" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">MR AI</div>
          <div className="brand-sub">STAN // COMMAND CENTER</div>
        </div>

        <div className="operator">
          <Core state={coreState} modActive={working} />
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
            <span className="eyebrow">VOICE COMMAND</span>
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
              if (/^(zima|lala|sleep|sleep mode)$/i.test(text.trim())) {
                handlePowerCommand("sleep");
              } else if (/^(amka|wake|wake up|amka mr ai)$/i.test(text.trim())) {
                handlePowerCommand("wake");
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

      <main className="main-area">
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
            <div className="mode-indicator">
              <span className="mode-label">{sleeping ? "SLEEP MODE" : working ? "WORKING MODE" : "NORMAL MODE"}</span>
              <span className="live-dot">{sleeping ? "PAUSED" : "LIVE"}</span>
            </div>
          </div>
        </header>

        <div className="content">
          {active === "dashboard" && (
            <DashboardHome
              system={system}
              telemetryHistory={telemetryHistory}
              agents={agents}
              radarFindings={radarFindings}
              tasks={tasks}
              memories={memories}
              activities={activities}
              coreState={coreState}
              working={working}
              onRefresh={refresh}
              onState={setCoreState}
              onModToggle={toggleMode}
              onPowerCommand={handlePowerCommand}
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
                  {["IDLE", "LISTENING", "THINKING", "SPEAKING", "WORKING", "BUSY", "ERROR", "SLEEPING"].map(state => (
                    <button className={coreState === state ? "state-active" : ""} key={state} onClick={() => setCoreState(state)}>{state}</button>
                  ))}
                </div>
                <div className="core-stage tall"><Core state={coreState} modActive={working} /></div>
              </div>
              <Chat onState={setCoreState} onModToggle={toggleMode} onPowerCommand={handlePowerCommand} />
            </section>
          )}

          {active === "agents" && <AgentsPanel agents={agents} onPlan={createPlan} />}
          {active === "browser" && <BrowserHands />}
          {active === "device" && <DeviceLab />}
          {active === "creative" && <CreativeStudio />}
          {active === "web" && <WebIntelligence />}
          {active === "gmail" && <GmailPanel />}
          {active === "map" && <TrackingMap />}
          {active === "security" && <SecurityHub />}
          {active === "tools" && <ToolBox />}

          {active === "tasks" && (
            <section className="panel large-panel">
              <div className="panel-head">
                <div><span className="eyebrow">TASK SYSTEM</span><h2>Durable Operations</h2></div>
              </div>
              <p className="empty">Tasks are persisted by the backend. Use the AI command channel to create and manage work; completion is only reported after backend confirmation.</p>
            </section>
          )}

          {active === "memory" && (
            <section className="panel large-panel">
              <div className="panel-head">
                <div><span className="eyebrow">MEMORY CORE</span><h2>User-approved memory</h2></div>
              </div>
              <p className="empty">Memory is handled through the existing authenticated backend routes. Secret values are never displayed by the dashboard.</p>
            </section>
          )}

          {active === "system" && (
            <section className="panel large-panel">
              <div className="panel-head">
                <div><span className="eyebrow">SYSTEM</span><h2>Verified Service State</h2></div>
              </div>
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
