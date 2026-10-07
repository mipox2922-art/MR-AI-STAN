export default function Core({ state = "IDLE", modActive = false }) {
  const tone = modActive ? "#ff5555" : "#00f3ff";
  const glow = modActive ? "rgba(255,85,85,.34)" : "rgba(0,243,255,.30)";
  const speaking = state === "SPEAKING";
  const thinking = ["THINKING", "WORKING", "BUSY"].includes(state);
  const listening = state === "LISTENING";
  const sleeping = state === "SLEEPING";

  return (
    <div
      className={`ai-core-hologram state-${state.toLowerCase()} ${modActive ? "mod-active" : ""}`}
      style={{ "--core-tone": tone, "--core-glow": glow }}
      aria-label={`MR AI ${state}`}
    >
      <div className="core-hologram-scan" />
      <svg className="core-hologram-svg" viewBox="0 0 300 270" role="img" aria-hidden="true">
        <ellipse cx="150" cy="132" rx="82" ry="105" className="face-silhouette" />
        <path d="M91 96 Q150 55 209 96 M88 118 Q150 94 212 118 M93 142 Q150 125 207 142 M103 168 Q150 155 197 168 M118 194 Q150 186 182 194" className="face-mesh" />
        <path d="M94 91 L79 115 L84 155 L104 187 M206 91 L221 115 L216 155 L196 187" className="face-mesh" />
        <path d="M136 112 L150 125 L143 154 L154 162" className="face-detail" />
        <path d="M126 184 Q150 193 174 184" className="face-detail" />
        <path d="M105 117 Q123 108 139 118 M161 118 Q177 108 195 117" className="face-eye-frame" />
        <ellipse cx="124" cy="119" rx="8" ry="4" className={`face-eye ${thinking || listening ? "active" : ""}`} />
        <ellipse cx="176" cy="119" rx="8" ry="4" className={`face-eye ${thinking || listening ? "active" : ""}`} />
        <path d={speaking ? "M132 185 Q150 202 168 185" : "M134 186 Q150 190 166 186"} className={`face-mouth ${speaking ? "speaking" : ""}`} />
        <path d="M73 208 Q150 242 227 208" className="face-base-line" />
      </svg>
      <div className="core-hologram-label">MR AI</div>
      <div className="core-hologram-state">{sleeping ? "SLEEP" : state}</div>
    </div>
  );
}
