import { useState, useEffect, useRef } from "react";

export default function MRAICommandCenter() {
  const [mode, setMode] = useState("normal");
  const [input, setInput] = useState("");
  const [clock, setClock] = useState(new Date());
  const [cpu, setCpu] = useState(32);
  const chatEndRef = useRef(null);

  const [messages, setMessages] = useState([
    { sender: "You", text: "Hey Ferisi, give me system update", time: "10:24 AM" },
    { sender: "MR AI", text: "All systems operational. 5 tasks in progress. System performance at optimum levels.", time: "10:24 AM" },
  ]);

  const isWorking = mode === "working";

  // theme colors
  const theme = isWorking
    ? { bg: "#140303", panel: "#1f0505", border: "#7a1414", accent: "#ff3b3b", accent2: "#c81e1e", glow: "rgba(255,59,59,0.45)", text: "#ffd0d0", dim: "#c47a7a" }
    : { bg: "#020c14", panel: "#04141f", border: "#0e5c7a", accent: "#22d3ee", accent2: "#0891b2", glow: "rgba(34,211,238,0.4)", text: "#bff3ff", dim: "#5fa9be" };

  const normalStats = { cpu: 32, mem: 45, net: 68, sto: 72, gpu: 58, learn: "98.7%", resp: "0.03s", status: "OPERATIONAL", threat: "LOW", mission: "Execute, monitor and optimize all assigned operations with precision and efficiency.", focus: "Project Pegasus - Phase 2." };
  const workingStats = { cpu: 78, mem: 82, net: 65, sto: 80, gpu: 72, learn: "98.9%", resp: "0.04s", status: "WORKING", threat: "HIGH", mission: "Executing system operations... Monitoring global network... Analyzing data streams...", focus: "Active Processing Mode." };
  const stats = isWorking ? workingStats : normalStats;

  // clock
  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // cpu jitter
  useEffect(() => {
    const t = setInterval(() => {
      setCpu(Math.max(5, Math.min(99, stats.cpu + Math.floor(Math.random() * 7 - 3))));
    }, 2200);
    return () => clearInterval(t);
  }, [stats.cpu]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const addMsg = (sender, text) => {
    const time = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    setMessages((m) => [...m, { sender, text, time }]);
  };

  const send = () => {
    if (!input.trim()) return;
    addMsg("You", input);
    const val = input.toLowerCase();
    if (val.includes("working")) setMode("working");
    if (val.includes("normal")) setMode("normal");
    setInput("");
    setTimeout(() => {
      const replies = isWorking
        ? ["Bado ninachambua mtandao... vitisho 3 vimegunduliwa.", "Ninaendelea kufanya kazi kwenye mifumo yote.", "Uchambuzi wa data unaendelea, subiri kidogo."]
        : ["Mifumo yote iko sawa na inafanya kazi vizuri.", "Nimepokea ombi lako, ninashughulikia sasa.", "Hakuna tatizo lolote kwa sasa."];
      addMsg("MR AI", replies[Math.floor(Math.random() * replies.length)]);
    }, 600);
  };

  const quickAction = (name) => addMsg("MR AI", `${name} inatekelezwa... ✔ Imekamilika.`);

  // ---- shared style helpers ----
  const panelStyle = {
    border: `1px solid ${theme.border}`,
    background: "linear-gradient(180deg, rgba(255,255,255,0.025), rgba(0,0,0,0.15))",
    borderRadius: 6,
    padding: 12,
    boxShadow: `0 0 20px -10px ${theme.glow} inset`,
  };
  const h2Style = {
    margin: "0 0 10px 0",
    fontSize: 11,
    letterSpacing: 1.5,
    color: theme.accent,
    textTransform: "uppercase",
    borderBottom: `1px solid ${theme.border}`,
    paddingBottom: 7,
    fontWeight: 700,
  };
  const barRow = (label, val) => (
    <div style={{ marginBottom: 8 }} key={label}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: theme.dim, marginBottom: 3 }}>
        <span>{label}</span>
        <b style={{ color: theme.text }}>{val}%</b>
      </div>
      <div style={{ height: 5, background: "rgba(255,255,255,0.06)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${val}%`, borderRadius: 3, background: `linear-gradient(90deg, ${theme.accent2}, ${theme.accent})`, boxShadow: `0 0 8px ${theme.glow}`, transition: "width 1s ease" }} />
      </div>
    </div>
  );
  const kvRow = (label, val, colorAccent) => (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, padding: "5px 0", borderBottom: "1px dashed rgba(255,255,255,0.06)" }} key={label}>
      <span style={{ color: theme.dim }}>{label}</span>
      <b style={{ color: colorAccent || theme.accent }}>{val}</b>
    </div>
  );

  const navItems = ["🏠 Dashboard", "🧠 AI Core", "🤖 Agents", "📋 Tasks", "📅 Calendar", "💾 Memory", "📁 Files", "💬 Communication", "📊 Analytics", "⚙️ System", "🔧 Settings"];
  const quickCommands = isWorking
    ? ["🔍 SCAN SYSTEM", "📊 ANALYZE DATA", "🌐 WEB RESEARCH", "📄 GENERATE REPORT", "🛡️ SECURITY SCAN", "⛔ TERMINATE THREATS"]
    : ["🔍 SCAN SYSTEM", "📊 ANALYZE DATA", "🌐 WEB RESEARCH", "📄 GENERATE REPORT", "🛡️ SECURITY CHECK", "⚙️ OPTIMIZE"];

  const researchNormal = [
    ["Global Technology Trends", "Latest AI and Tech Updates"],
    ["Cybersecurity News", "Threats and Protection Strategies"],
    ["Market Analysis", "Financial Markets Overview"],
    ["Science & Innovation", "Breakthrough Technologies"],
  ];
  const researchWorking = [
    ["Global Threat Intelligence", "Latest Cyber Threats"],
    ["Security Best Practices", "Network Protection Strategies"],
    ["AI in Cybersecurity", "Advanced Defense Systems"],
    ["Tech Market Trends", "Global Technology Insights"],
  ];
  const research = isWorking ? researchWorking : researchNormal;

  return (
    <div style={{ background: theme.bg, color: theme.text, fontFamily: "'Segoe UI', Arial, sans-serif", minHeight: "100vh", padding: 12, transition: "background 0.5s ease" }}>
      <style>{`
        * { box-sizing: border-box; }
        body { margin: 0; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-thumb { background: ${theme.border}; border-radius: 3px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
        @keyframes wv { 0%,100% { height: 20%; } 50% { height: 100%; } }
        .qbtn:hover { background: ${theme.glow} !important; color: #000 !important; border-color: ${theme.accent} !important; }
        nav a:hover { color: ${theme.text} !important; background: rgba(255,255,255,0.03) !important; }
      `}</style>

      <div style={{ maxWidth: 1500, margin: "0 auto" }}>
        {/* TOP BAR */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", border: `1px solid ${theme.border}`, borderRadius: 6, padding: "10px 20px", marginBottom: 10, boxShadow: `0 0 24px -8px ${theme.glow} inset` }}>
          <h1 style={{ margin: 0, fontSize: 19, letterSpacing: 4, fontWeight: 700, color: theme.accent, textTransform: "uppercase" }}>
            MR AI Command Center {isWorking && "// WORKING MODE"}
          </h1>
          <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 12, color: theme.dim, letterSpacing: 1 }}>
            <span>{clock.toLocaleTimeString("en-GB")}</span>
            <span>{clock.toLocaleDateString("sw-TZ", { weekday: "short", year: "numeric", month: "short", day: "2-digit" })}</span>
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: theme.accent, fontWeight: 600 }}>
              <div style={{ width: 7, height: 7, borderRadius: "50%", background: theme.accent, boxShadow: `0 0 8px ${theme.glow}`, animation: "pulse 1.6s infinite" }} />
              {isWorking ? "WORKING MODE" : "NORMAL MODE"}
            </div>
            <div style={{ display: "flex", border: `1px solid ${theme.border}`, borderRadius: 6, overflow: "hidden", cursor: "pointer" }}>
              <div onClick={() => setMode("normal")} style={{ padding: "7px 12px", fontSize: 10.5, fontWeight: 700, letterSpacing: 1.5, color: !isWorking ? "#000" : theme.dim, background: !isWorking ? theme.accent : "transparent" }}>NORMAL</div>
              <div onClick={() => setMode("working")} style={{ padding: "7px 12px", fontSize: 10.5, fontWeight: 700, letterSpacing: 1.5, color: isWorking ? "#000" : theme.dim, background: isWorking ? theme.accent : "transparent" }}>WORKING</div>
            </div>
          </div>
        </div>

        {/* MAIN GRID */}
        <div style={{ display: "grid", gridTemplateColumns: "210px 1fr 1.6fr 1fr 1fr", gap: 10 }}>

          {/* SIDEBAR */}
          <div style={{ ...panelStyle, gridColumn: 1, gridRow: "1 / 3", display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14 }}>
              <div style={{ width: 48, height: 48, borderRadius: "50%", border: `2px solid ${theme.accent}`, background: `radial-gradient(circle at 35% 30%, ${theme.accent}, #000 75%)`, boxShadow: `0 0 16px ${theme.glow}`, flexShrink: 0 }} />
              <div>
                <div style={{ fontWeight: 700, fontSize: 12.5 }}>BOSS FERISI</div>
                <div style={{ fontSize: 10.5, color: theme.dim }}>Chief of Staff</div>
                <div style={{ fontSize: 9.5, color: theme.accent, display: "flex", alignItems: "center", gap: 4, marginTop: 2 }}>
                  <div style={{ width: 6, height: 6, borderRadius: "50%", background: theme.accent }} /> ONLINE
                </div>
              </div>
            </div>
            <nav>
              {navItems.map((item, i) => (
                <a key={item} style={{
                  display: "flex", alignItems: "center", gap: 9, padding: "8px 9px", fontSize: 11.5,
                  color: i === 0 ? theme.accent : theme.dim, textDecoration: "none", borderRadius: 4, marginBottom: 1,
                  borderLeft: i === 0 ? `2px solid ${theme.accent}` : "2px solid transparent",
                  background: i === 0 ? `linear-gradient(90deg, ${theme.glow}, transparent)` : "transparent",
                  fontWeight: i === 0 ? 600 : 400, cursor: "pointer",
                }}>{item}</a>
              ))}
            </nav>
            <div style={{ marginTop: "auto", border: `1px solid ${theme.border}`, borderRadius: 6, padding: 11, background: "rgba(0,0,0,0.2)" }}>
              <div style={{ fontSize: 9.5, letterSpacing: 1.5, color: theme.accent, marginBottom: 7 }}>{isWorking ? "VOICE COMMANDS" : "VOICE COMMAND"}</div>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 22, marginBottom: 7 }}>
                {[0, 0.1, 0.2, 0.3, 0.15, 0.25, 0.05, 0.35].map((d, i) => (
                  <span key={i} style={{ width: 3, background: theme.accent, borderRadius: 2, animation: `wv 1s infinite ease-in-out`, animationDelay: `${d}s`, boxShadow: `0 0 6px ${theme.glow}`, height: "60%" }} />
                ))}
              </div>
              <div style={{ fontSize: 10, color: theme.dim }}>{isWorking ? 'Processing... "Accessing system..."' : 'Listening... "Hey Ferisi, I\\'m at your service."'}</div>
              <div style={{ marginTop: 7, width: 30, height: 30, borderRadius: "50%", border: `1px solid ${theme.accent}`, display: "flex", alignItems: "center", justifyContent: "center", color: theme.accent, fontSize: 13 }}>🎙️</div>
            </div>
          </div>

          {/* SYSTEM STATUS */}
          <div style={{ ...panelStyle, gridColumn: 2, gridRow: 1 }}>
            <div style={h2Style}>System Status</div>
            {barRow("CPU USAGE", cpu)}
            {barRow("MEMORY", stats.mem)}
            {barRow("NETWORK", stats.net)}
            {barRow("STORAGE", stats.sto)}
            {barRow("GPU", stats.gpu)}
          </div>

          {/* AI CORE STATUS */}
          <div style={{ ...panelStyle, gridColumn: 3, gridRow: 1, display: "flex", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={h2Style}>AI Core Status</div>
              {kvRow("AI MODEL", "JARVIS v2.6")}
              {kvRow("LEARNING RATE", stats.learn)}
              {kvRow("RESPONSE TIME", stats.resp)}
              {kvRow("UPTIME", "12d 08h 24m")}
              {kvRow("STATUS", stats.status, isWorking ? theme.accent : "#22ff8c")}
            </div>
            <div style={{ width: 80, flexShrink: 0, borderRadius: 6, background: `radial-gradient(circle at 50% 35%, ${theme.glow}, transparent 65%)`, border: `1px solid ${theme.border}`, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <div style={{ display: "flex", gap: 10 }}>
                <i style={{ width: 6, height: 6, borderRadius: "50%", background: theme.accent, boxShadow: `0 0 12px 4px ${theme.glow}`, display: "block" }} />
                <i style={{ width: 6, height: 6, borderRadius: "50%", background: theme.accent, boxShadow: `0 0 12px 4px ${theme.glow}`, display: "block" }} />
              </div>
            </div>
          </div>

          {/* MISSION OVERVIEW */}
          <div style={{ ...panelStyle, gridColumn: "4 / 6", gridRow: 1, display: "flex", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={h2Style}>Mission Overview</div>
              <div style={{ fontSize: 11.5, color: theme.dim, lineHeight: 1.6 }}>{stats.mission}</div>
              <div style={{ marginTop: 8, fontSize: 11.5 }}>
                Current Focus:<br /><b style={{ color: theme.accent }}>{stats.focus}</b>
              </div>
            </div>
            <div style={{ width: 170, flexShrink: 0 }}>
              <svg viewBox="0 0 170 60" preserveAspectRatio="none" style={{ width: "100%", height: 60, display: "block" }}>
                <polyline points="0,50 20,42 40,45 60,30 80,35 100,20 120,25 140,10 160,15" fill="none" stroke={theme.accent} strokeWidth="1.5" />
              </svg>
              <div style={{ width: 34, height: 34, borderRadius: "50%", margin: "6px auto 0", background: `radial-gradient(circle at 40% 35%, ${theme.glow}, transparent 65%)`, border: `1px solid ${theme.border}` }} />
            </div>
          </div>

          {/* RADAR */}
          <div style={{ ...panelStyle, gridColumn: 2, gridRow: 2 }}>
            <div style={h2Style}>Radar Scan</div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
              <div style={{ width: 150, height: 150, borderRadius: "50%", position: "relative", border: `1px solid ${theme.border}`, overflow: "hidden" }}>
                <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", background: `conic-gradient(from 0deg, ${theme.glow}, transparent 40deg)`, animation: "spin 3s linear infinite", borderRadius: "50%" }} />
                <div style={{ position: "absolute", top: "40%", left: "60%", width: 5, height: 5, borderRadius: "50%", background: theme.accent, boxShadow: `0 0 8px ${theme.glow}` }} />
                <div style={{ position: "absolute", top: "65%", left: "30%", width: 5, height: 5, borderRadius: "50%", background: theme.accent, boxShadow: `0 0 8px ${theme.glow}` }} />
                <div style={{ position: "absolute", top: "25%", left: "75%", width: 5, height: 5, borderRadius: "50%", background: theme.accent, boxShadow: `0 0 8px ${theme.glow}` }} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", width: "100%", fontSize: 9.5, color: theme.dim, marginTop: 7 }}>
                <span>GLOBAL SCAN<br /><b style={{ color: theme.accent }}>ACTIVE</b></span>
                <span style={{ textAlign: "right" }}>THREATS<br /><b style={{ color: theme.accent }}>{stats.threat}</b></span>
              </div>
            </div>
          </div>

          {/* MAP */}
          <div style={{ ...panelStyle, gridColumn: 3, gridRow: 2, display: "flex", flexDirection: "column", alignItems: "center" }}>
            <div style={{ ...h2Style, alignSelf: "flex-start" }}>Global Network</div>
            <div style={{ width: "100%", maxWidth: 230, height: 230, borderRadius: "50%", position: "relative", border: `1px solid ${theme.border}`, background: `radial-gradient(circle at 40% 35%, ${theme.glow}, transparent 65%)`, overflow: "hidden" }}>
              <div style={{ position: "absolute", inset: 0, borderRadius: "50%", border: `1px solid ${theme.border}`, animation: "spin 12s linear infinite" }} />
              <div style={{ position: "absolute", top: "20%", left: "30%", width: 8, height: 8, borderRadius: "50% 50% 50% 0", transform: "rotate(-45deg)", background: theme.accent, boxShadow: `0 0 8px ${theme.accent}` }} />
              <div style={{ position: "absolute", top: "55%", left: "20%", width: 8, height: 8, borderRadius: "50% 50% 50% 0", transform: "rotate(-45deg)", background: "#22ff8c", boxShadow: "0 0 8px #22ff8c" }} />
              <div style={{ position: "absolute", top: "30%", left: "70%", width: 8, height: 8, borderRadius: "50% 50% 50% 0", transform: "rotate(-45deg)", background: theme.accent, boxShadow: `0 0 8px ${theme.accent}` }} />
              <div style={{ position: "absolute", top: "65%", left: "60%", width: 8, height: 8, borderRadius: "50% 50% 50% 0", transform: "rotate(-45deg)", background: theme.accent, boxShadow: `0 0 8px ${theme.accent}` }} />
            </div>
            <div style={{ fontSize: 10, color: theme.dim, marginTop: 8 }}>📍 Global Monitoring Grid</div>
            <div style={{ marginTop: 8, fontSize: 10.5, color: theme.dim, lineHeight: 1.7, width: "100%" }}>
              {isWorking ? (
                <>
                  <div style={{ color: theme.accent }}>&gt; SCANNING global network...</div>
                  <div style={{ color: theme.accent }}>&gt; THREAT ANALYSIS in progress...</div>
                  <div>&gt; SYSTEM CHECK: 72%</div>
                  <div style={{ color: theme.accent }}>&gt; 3 THREATS DETECTED — analyzing...</div>
                </>
              ) : (
                <>
                  <div>&gt; System nominal. Monitoring active nodes.</div>
                  <div>&gt; No anomalies detected.</div>
                </>
              )}
            </div>
          </div>

          {/* CHAT */}
          <div style={{ ...panelStyle, gridColumn: 4, gridRow: 2, display: "flex", flexDirection: "column" }}>
            <div style={h2Style}>MR AI Chat</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 7, maxHeight: 150, overflowY: "auto", marginBottom: 9, flex: 1 }}>
              {messages.map((m, i) => (
                <div key={i} style={{ border: `1px solid ${theme.border}`, borderRadius: 6, padding: "7px 9px", fontSize: 10.8, background: "rgba(255,255,255,0.02)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", color: theme.accent, fontWeight: 700, fontSize: 9.5, marginBottom: 3, letterSpacing: 1 }}>
                    <span>{m.sender.toUpperCase()}</span><span style={{ color: theme.dim, fontWeight: 400 }}>{m.time}</span>
                  </div>
                  <p style={{ margin: 0, color: theme.text }}>{m.text}</p>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && send()}
                placeholder="Type a message..."
                style={{ flex: 1, background: "rgba(0,0,0,0.3)", border: `1px solid ${theme.border}`, borderRadius: 4, padding: "7px 9px", color: theme.text, fontSize: 11, outline: "none" }}
              />
              <button onClick={send} style={{ background: theme.accent, border: "none", color: "#000", fontWeight: 700, borderRadius: 4, padding: "0 12px", cursor: "pointer" }}>➤</button>
            </div>
          </div>

          {/* WEB RESEARCH */}
          <div style={{ ...panelStyle, gridColumn: 5, gridRow: 2 }}>
            <div style={h2Style}>Web Research</div>
            <div style={{ display: "flex", border: `1px solid ${theme.border}`, borderRadius: 4, overflow: "hidden", marginBottom: 10 }}>
              <input placeholder="Search information..." style={{ flex: 1, background: "rgba(0,0,0,0.3)", border: "none", padding: "7px 9px", color: theme.text, fontSize: 11, outline: "none" }} />
              <button style={{ background: theme.accent, border: "none", color: "#000", padding: "0 11px", cursor: "pointer", fontWeight: 700 }}>🔍</button>
            </div>
            {research.map(([t, s]) => (
              <div key={t} style={{ padding: "7px 0", borderBottom: "1px dashed rgba(255,255,255,0.06)" }}>
                <div style={{ fontSize: 11.5, fontWeight: 600, color: theme.text }}>{t}</div>
                <div style={{ fontSize: 10, color: theme.dim }}>{s}</div>
              </div>
            ))}
          </div>

          {/* QUICK COMMANDS */}
          <div style={{ ...panelStyle, gridColumn: "1 / 6", gridRow: 3, display: "flex", gap: 9, flexWrap: "wrap" }}>
            {quickCommands.map((cmd) => (
              <div key={cmd} className="qbtn" onClick={() => quickAction(cmd)} style={{ flex: 1, minWidth: 130, border: `1px solid ${theme.border}`, borderRadius: 6, padding: "11px 10px", textAlign: "center", fontSize: 10.5, letterSpacing: 1, color: theme.text, background: "rgba(255,255,255,0.02)", cursor: "pointer", fontWeight: 600 }}>
                {cmd}
              </div>
            ))}
          </div>

        </div>
      </div>
    </div>
  );
}
