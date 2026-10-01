export default function Core({ state = "IDLE", modActive = false }) {
  const tone = modActive ? "#ff5555" : "#00f3ff";
  const glow = modActive
    ? "rgba(255,85,85,.38)"
    : "rgba(0,243,255,.32)";

  const speaking = state === "SPEAKING";
  const listening = state === "LISTENING";
  const thinking = state === "THINKING" || state === "WORKING" || state === "BUSY";
  const sleeping = state === "SLEEPING";

  return (
    <div
      className={`ai-core state-${state.toLowerCase()} ${modActive ? "mod-active" : ""}`}
      style={{ "--core-tone": tone, "--core-glow": glow }}
      aria-label={`MR AI ${state}`}
    >
      <div className="core-ring ring-one" />
      <div className={`core-ring ring-two ${thinking ? "core-ring-fast" : ""}`} />
      <div className={`core-ring ring-three ${speaking || listening ? "core-ring-pulse" : ""}`} />

      <div className={`core-center ${sleeping ? "core-sleeping" : ""}`}>
        <div className="core-face" aria-hidden="true">
          <span className={`core-eye ${thinking ? "core-eye-active" : ""}`} />
          <span className={`core-eye ${thinking ? "core-eye-active" : ""}`} />
          <span className={`core-mouth ${speaking ? "core-mouth-speaking" : ""}`} />
        </div>
        <span className="core-name">MR</span>
        <small>AI</small>
      </div>

      <div className="core-state">{sleeping ? "SLEEP" : state}</div>
    </div>
  );
}
