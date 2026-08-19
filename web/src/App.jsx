import { useEffect, useState } from "react";

import Sidebar from "./components/Sidebar";
import Core from "./components/Core";
import Chat from "./components/Chat";
import Status from "./components/Status";
import Activity from "./components/Activity";

import {
  login,
  register,
  getStatus,
  getToken
} from "./api";

export default function App() {
  const [authenticated, setAuthenticated] =
    useState(Boolean(getToken()));

  const [username, setUsername] = useState("boss");
  const [password, setPassword] = useState("");

  const [active, setActive] = useState("CORE");
  const [state, setState] = useState("IDLE");
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!authenticated) return;

    getStatus()
      .then(setStatus)
      .catch(() => {});
  }, [authenticated]);

  async function authenticate(mode) {
    setError("");

    try {
      if (mode === "register") {
        await register(username, password);
      } else {
        await login(username, password);
      }

      setAuthenticated(true);

    } catch (err) {
      setError(err.message);
    }
  }

  if (!authenticated) {
    return (
      <div className="login-screen">
        <div className="login-box">
          <div className="login-core">MR AI</div>

          <h1>MR AI</h1>
          <p>DIGITAL CHIEF OF STAFF</p>

          <input
            value={username}
            onChange={e => setUsername(e.target.value)}
            placeholder="Username"
          />

          <input
            value={password}
            onChange={e => setPassword(e.target.value)}
            type="password"
            placeholder="Password"
          />

          {error && (
            <div className="error">
              {error}
            </div>
          )}

          <button onClick={() => authenticate("login")}>
            LOGIN
          </button>

          <button
            className="secondary"
            onClick={() => authenticate("register")}
          >
            CREATE BOSS ACCOUNT
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <Sidebar
        active={active}
        setActive={setActive}
      />

      <main className="main">
        <header className="topbar">
          <div>
            <span className="system-label">
              MR-AI-CHIEF-OF-STAFF
            </span>
            <h1>{active}</h1>
          </div>

          <div className="live">
            <span />
            SYSTEM ONLINE
          </div>
        </header>

        {active === "CORE" && (
          <div className="dashboard">
            <div className="core-area">
              <Core state={state} />

              <div className="greeting">
                <strong>Boss Ferisi</strong>
                <span>
                  Digital Chief of Staff ready.
                </span>
              </div>
            </div>

            <Chat onState={setState} />

            <Status status={status} />

            <Activity />
          </div>
        )}

        {active !== "CORE" && (
          <div className="module-placeholder">
            <div className="placeholder-core">
              MR AI
            </div>

            <h2>{active}</h2>

            <p>
              Module architecture ready.
              Phase 1 implementation itaendelea hapa.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
