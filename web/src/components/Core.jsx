export default function Core({ state = "IDLE", modActive = true }) {
  return () => clearTimeout(timer);
  }, [modActive]);

  return (
    <div
      className={`ai-core state-${state.toLowerCase()} ${
        modActive ? "mod-active" : ""
      }`}
      style={{
        filter: modActive ? "drop-shadow(0 0 30px rgba(255, 85, 85, 0.8))" : "none"
      }}
    >
      {chunks.map((chunk) => (
        <div
          key={chunk.id}
          className="chunk"
          style={{
            left: `${chunk.left}%`,
            animationDelay: `${chunk.delay}s`
          }}
        />
      ))}

      <div 
        className="core-ring ring-one"
        style={{
          borderColor: modActive ? "#ff5555" : "#00f3ff",
          boxShadow: modActive 
            ? "0 0 20px rgba(255, 85, 85, 0.4), inset 0 0 20px rgba(255, 85, 85, 0.15)"
            : "0 0 20px rgba(0, 243, 255, 0.3), inset 0 0 20px rgba(0, 243, 255, 0.1)"
        }}
      />
      <div 
        className="core-ring ring-two"
        style={{
          borderColor: modActive ? "#ff5555" : "#00f3ff",
          boxShadow: modActive 
            ? "0 0 20px rgba(255, 85, 85, 0.4), inset 0 0 20px rgba(255, 85, 85, 0.15)"
            : "0 0 20px rgba(0, 243, 255, 0.3), inset 0 0 20px rgba(0, 243, 255, 0.1)"
        }}
      />
      <div 
        className="core-ring ring-three"
        style={{
          borderColor: modActive ? "#ff5555" : "#00f3ff"
        }}
      />

      <div 
        className="core-center"
        style={{
          borderColor: modActive ? "#ff5555" : "#00f3ff",
          color: modActive ? "#ff5555" : "#00f3ff",
          boxShadow: modActive
            ? "0 0 30px rgba(255, 85, 85, 0.5), inset 0 0 30px rgba(255, 85, 85, 0.2)"
            : "0 0 30px rgba(0, 243, 255, 0.4), inset 0 0 30px rgba(0, 243, 255, 0.12)"
        }}
      >
        <span>MR</span>
        <small>AI</small>
      </div>

      <div 
        className="core-state"
        style={{ color: modActive ? "#ff5555" : "#00f3ff" }}
      >
        {state}
      </div>

    </div>
  );
}
