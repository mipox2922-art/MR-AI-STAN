import { useEffect, useState } from "react";

const BOOT_STEPS = [
  "INITIALIZING MR AI HUD",
  "CALIBRATING COMMAND PANELS",
  "BINDING RUNTIME READOUTS",
  "SYNCING AUTHORIZED MODULES",
  "COMMAND INTERFACE READY",
];

export default function CommandBoot({ onFinish }) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      onFinish();
      return undefined;
    }

    let value = 0;
    let finishTimer;
    const timer = window.setInterval(() => {
      value = Math.min(100, value + 8);
      setProgress(value);
      if (value >= 100) {
        window.clearInterval(timer);
        finishTimer = window.setTimeout(onFinish, 420);
      }
    }, 95);

    return () => {
      window.clearInterval(timer);
      window.clearTimeout(finishTimer);
    };
  }, [onFinish]);

  const stepIndex = Math.min(BOOT_STEPS.length - 1, Math.floor(progress / 21));

  return (
    <section className="mrai-boot" role="dialog" aria-modal="true" aria-label="MR AI Command Center initialization">
      <div className="mrai-boot-card">
        <svg className="mrai-boot-orbit" viewBox="0 0 200 200" aria-hidden="true">
          <circle className="orbit-outer" cx="100" cy="100" r="88" />
          <circle className="orbit-dash" cx="100" cy="100" r="71" />
          <circle className="orbit-inner" cx="100" cy="100" r="52" />
          <path className="orbit-cross" d="M100 18V182M18 100H182M42 42L158 158M158 42L42 158" />
          <polygon points="100,62 133,81 133,119 100,138 67,119 67,81" />
          <circle className="orbit-core" cx="100" cy="100" r="18" />
          <circle className="orbit-dot" cx="100" cy="100" r="6" />
        </svg>
        <div className="mrai-boot-brand">MR AI</div>
        <div className="mrai-boot-subtitle">STAN // COMMAND CENTER</div>
        <div className="mrai-boot-owner">MOG343 OPERATIONS · BOSS FERISI</div>
        <div className="mrai-boot-progress" role="progressbar" aria-label="Interface initialization" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
          <span style={{ width: `${progress}%` }} />
        </div>
        <div className="mrai-boot-progress-line">
          <span>{BOOT_STEPS[stepIndex]}</span>
          <strong>{progress}%</strong>
        </div>
        <div className="mrai-boot-terminal" aria-live="polite">
          {BOOT_STEPS.slice(0, stepIndex + 1).map((step, index) => (
            <div key={step} className={index === stepIndex ? "current" : ""}>
              <span>{index < stepIndex ? "✓" : "›"}</span> {step}
              {index < stepIndex && <b>OK</b>}
            </div>
          ))}
          <small>UI INITIALIZATION ONLY · LIVE SERVICE STATUS IS SHOWN IN THE DASHBOARD</small>
        </div>
        <button type="button" className="mrai-boot-skip" onClick={onFinish}>SKIP INTRO ↗</button>
      </div>
    </section>
  );
}
