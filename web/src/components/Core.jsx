export default function Core({ state = "IDLE" }) {
  return (
    <div className={`ai-core state-${state.toLowerCase()}`}>
      <div className="core-ring ring-one" />
      <div className="core-ring ring-two" />
      <div className="core-ring ring-three" />

      <div className="core-center">
        <span>MR</span>
        <small>AI</small>
      </div>

      <div className="core-state">
        {state}
      </div>
    </div>
  );
}
