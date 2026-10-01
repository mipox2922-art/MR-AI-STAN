import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getAgents,
  getStatus,
  getToken,
  login,
  register,
  planAgentWork,
} from "./api";
import Chat from "./components/Chat";
import Core from "./components/Core";
import Activity from "./components/Activity";
import BrowserHands from "./components/BrowserHands";
import DeviceLab from "./components/DeviceLab";
import CreativeStudio from "./components/CreativeStudio";

const NAV = [
  ["dashboard", "⌂", "Dashboard"],
  ["core", "◉", "AI Core"],
  ["agents", "◆", "Agents"],
  ["browser", "↗", "Browser Hands"],
  ["device", "⌁", "Device Lab"],
  ["creative", "✦", "Creative Studio"],
  ["tasks", "✓", "Tasks"],
  ["memory", "◇", "Memory"],
  ["system", "⌘", "System"],
];

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

function Metric({ label, value }) {
  const number = Number(value);
  const known = Number.isFinite(number);
  return (
    <div className="metric">
      <div className="metric-head">
        <span>{label}</span>
        <strong>{known ? String(number) + "%" : "N/A"}</strong>
      </div>
      <div className="metric-bar">
        {known && <span style={{ width: Math.max(0, Math.min(100, number)) + "%" }} />}
      </div>
    </div>
  );
}

function Radar({ agents, working }) {
  const visible = agents.slice(0, 10);
  return (
    <div className="radar">
      <div className={`radar-sweep ${working ? "radar-sweep-active" : ""}`} />
      <div className="radar-grid grid-a" />
      <div className="radar-grid grid-b" />
      <div className="radar-cross vertical" />
      <div className="radar-cross horizontal" />
      {visible.map((agent, index) => {
        const angle = (index / Math.max(1, visible.length)) * Math.PI * 2;
        const radius = 26 + (index % 3) * 14;
        const x = 50 + Math.cos(angle) * radius;
        const y = 50 + Math.sin(angle) * radius;
        return (
          <span
            key={agent.id}
            className="radar-dot"
            title={agent.name}
            style={{ left: x + "%", top: y + "%" }}
          />
        );
      })}
      <div className="radar-core">MR</div>
    </div>
  );
}

function AgentsPanel({ agents, onPlan }) {
  const [request, setRequest] = useState("");
  const [plan, setPlan] = useState(null);

  async function plan() {
    if (!request.trim()) return;
    try {
      const result = await onPlan(request.trim());
      setPlan(result);
    } catch (error) {
      setPlan({ status: "ERROR", reason: error.message });
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
          <button onClick={plan}>PLAN</button>
        </div>
        {plan && (
          <pre className="plan-output">{JSON.stringify(plan, null, 2)}</pre>
        )}
      </div>
    </section>
  );
}

function App() {
  const [token, setTokenState] = useState(getToken());
  const [active, setActive] = useState("dashboard");
  const [mode, setMode] = useState("normal");
  const [coreState, setCoreState] = useState("IDLE");
  const [system, setSystem] = useState(null);
  const [agents, setAgents] = useState([]);
  const [clock, setClock] = useState(new Date());

  const authenticated = Boolean(token);

  const refresh = useCallback(async () => {
    if (!getToken()) return;
    try {
      const [status, fleet] = await Promise.all([getStatus(), getAgents()]);
      setSystem(status);
      setAgents(fleet);
    } catch (error) {
      if (/401|unauthorized/i.test(error.message)) {
        localStorage.removeItem("mr_ai_token");
        setTokenState(null);
      }
    }
  }, []);

  useEffect(() => {
    if (!authenticated) return undefined;
    refresh();
    const timer = setInterval(refresh, 5000);
    const clockTimer = setInterval(() => setClock(new Date()), 1000);
    return () => {
      clearInterval(timer);
      clearInterval(clockTimer);
    };
  }, [authenticated, refresh]);

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

  return (
    <div className={`app-shell ${working ? "mode-working" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">MR AI</div>
          <div className="brand-sub">STAN // COMMAND CENTER</div>
        </div>

        <div className="operator">
          <Core state={coreState} modActive={working} />
          <div>
            <strong>BOSS FERISI</strong>
            <span>CHIEF OF STAFF</span>
          </div>
        </div>

        <nav>
          {NAV.map(([id, icon, label]) => (
            <button className={active === id ? "active" : ""} onClick={() => setActive(id)} key={id}>
              <span>{icon}</span>{label}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button className={working ? "danger-button" : "primary-button"} onClick={() => setMode(working ? "normal" : "working")}>
            {working ? "NORMAL MODE" : "WORKING MODE"}
          </button>
          <button className="ghost-button" onClick={logout}>DISCONNECT SESSION</button>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div>
            <span className="eyebrow">MR AI STAN</span>
            <h1>{NAV.find(item => item[0] === active)?.[2] || "Command Center"}</h1>
          </div>
          <div className="top-status">
            <div>
              <strong>{clock.toLocaleTimeString("sw-TZ", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</strong>
              <span>{clock.toLocaleDateString("sw-TZ", { weekday: "short", day: "2-digit", month: "short", year: "numeric" })}</span>
            </div>
            <span className="live-dot">LIVE</span>
          </div>
        </header>

        <div className="content">
          {active === "dashboard" && (
            <>
              <section className="hero-grid">
                <div className="panel core-panel">
                  <div className="panel-head">
                    <div>
                      <span className="eyebrow">AI CORE</span>
                      <h2>MR AI Presence</h2>
                    </div>
                    <span className="badge">{coreState}</span>
                  </div>
                  <div className="core-stage">
                    <Core state={coreState} modActive={working} />
                  </div>
                  <p className="mission-line">
                    {working ? "Executing verified operations and coordinating active agents." : "Ready for your next command. No fake task-completion claims."}
                  </p>
                </div>

                <div className="panel">
                  <div className="panel-head">
                    <div>
                      <span className="eyebrow">TELEMETRY</span>
                      <h2>Real System State</h2>
                    </div>
                    <button className="mini-button" onClick={refresh}>REFRESH</button>
                  </div>
                  <Metric label="CPU" value={telemetry.cpu_percent} />
                  <Metric label="MEMORY" value={telemetry.memory_percent} />
                  <Metric label="STORAGE" value={telemetry.storage_percent} />
                  <Metric label="GPU" value={telemetry.gpu?.utilization_percent} />
                  <div className="stat-strip">
                    <div><span>UPTIME</span><strong>{uptimeLabel}</strong></div>
                    <div><span>GEMINI</span><strong>{services.gemini || "N/A"}</strong></div>
                    <div><span>KIMI</span><strong>{services.kimi || "N/A"}</strong></div>
                  </div>
                </div>

                <div className="panel radar-panel">
                  <div className="panel-head">
                    <div>
                      <span className="eyebrow">LIVE RADAR</span>
                      <h2>Agent Activity</h2>
                    </div>
                    <span className="badge">{agents.length} ONLINE</span>
                  </div>
                  <Radar agents={agents} working={working} />
                  <p className="radar-note">Markers represent registered agents. No fabricated threat locations.</p>
                </div>
              </section>

              <section className="split-grid">
                <Chat
                  onState={setCoreState}
                  onModToggle={value => setMode(value ? "working" : "normal")}
                />
                <Activity />
              </section>
            </>
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
              <Chat onState={setCoreState} onModToggle={value => setMode(value ? "working" : "normal")} />
            </section>
          )}

          {active === "agents" && <AgentsPanel agents={agents} onPlan={createPlan} />}
          {active === "browser" && <BrowserHands />}
          {active === "device" && <DeviceLab />}
          {active === "creative" && <CreativeStudio />}

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
