import { useEffect, useRef } from "react";

const SIZE = 420;

function pointsOnSphere(count) {
  const points = [];
  for (let i = 0; i < count; i += 1) {
    const y = 1 - (2 * (i + 0.5)) / count;
    const radius = Math.sqrt(1 - y * y);
    const angle = i * 2.39996;
    const spread = Math.random() < 0.2 ? 1 + Math.random() * 0.3 : 1;
    points.push([
      Math.cos(angle) * radius * spread,
      y * spread,
      Math.sin(angle) * radius * spread,
    ]);
  }
  return points;
}

function orbitalParticles(count) {
  return Array.from({ length: count }, () => {
    const y = Math.random() * 2 - 1;
    const angle = Math.random() * Math.PI * 2;
    const radius = Math.sqrt(1 - y * y);
    return [Math.cos(angle) * radius, y, Math.sin(angle) * radius, Math.random()];
  });
}

export default function HudOrb({ working = false, state = "IDLE" }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return undefined;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const root = canvas.closest(".app-shell") || document.documentElement;
    const theme = getComputedStyle(root);
    const orbColor = (theme.getPropertyValue("--av").trim() || (working ? "#ffd36a" : "#ffb52e"));
    const orbitColor = working ? "#ffd36a" : "#ffb52e";
    const surface = SIZE;
    const spherePoints = pointsOnSphere(520);
    const dust = orbitalParticles(80);
    const rings = [
      [0.55, 0.7, 0.8, 0],
      [0.72, 1.5, -0.6, 0.5],
      [0.88, 2.2, 0.45, 1],
      [1.02, 0.3, -0.35, 1.7],
      [1.17, 1.1, 0.25, 2.4],
    ];
    let mouseX = 0;
    let mouseY = 0;
    let frameId = 0;
    let disposed = false;

    canvas.width = surface;
    canvas.height = surface;
    context.setTransform(1, 0, 0, 1, 0, 0);

    function trackPointer(event) {
      mouseX = event.clientX / Math.max(1, window.innerWidth) - 0.5;
      mouseY = event.clientY / Math.max(1, window.innerHeight) - 0.5;
    }

    function project(x, y, z, yaw, pitch) {
      const x1 = x * Math.cos(yaw) + z * Math.sin(yaw);
      const z1 = -x * Math.sin(yaw) + z * Math.cos(yaw);
      const y2 = y * Math.cos(pitch) - z1 * Math.sin(pitch);
      const z2 = y * Math.sin(pitch) + z1 * Math.cos(pitch);
      const perspective = 3.4 / (3.4 + z2);
      return [
        surface / 2 + x1 * perspective * surface * 0.34,
        surface / 2 + y2 * perspective * surface * 0.34,
        z2,
      ];
    }

    function drawArc(radius, tilt, spin, start, end, yaw, pitch) {
      context.beginPath();
      for (let i = 0; i <= 60; i += 1) {
        const angle = start + ((end - start) * i) / 60;
        const x0 = Math.cos(angle) * radius;
        const y0 = Math.sin(angle) * radius * Math.cos(tilt);
        const z0 = Math.sin(angle) * radius * Math.sin(tilt);
        const x = x0 * Math.cos(spin) + z0 * Math.sin(spin);
        const z = -x0 * Math.sin(spin) + z0 * Math.cos(spin);
        const projected = project(x, y0, z, yaw, pitch);
        if (i === 0) context.moveTo(projected[0], projected[1]);
        else context.lineTo(projected[0], projected[1]);
      }
      context.stroke();
    }

    function draw(timestamp) {
      if (disposed) return;
      const pace = state === "SPEAKING" ? 1.45 : ["THINKING", "WORKING", "BUSY"].includes(state) ? 1.2 : 1;
      const time = (timestamp / 1000) * pace;
      const yaw = time * 0.35 + mouseX * 1.4;
      const pitch = 0.35 + mouseY * 0.6;

      context.clearRect(0, 0, surface, surface);
      context.globalCompositeOperation = "lighter";

      const glow = context.createRadialGradient(surface / 2, surface / 2, 0, surface / 2, surface / 2, surface * 0.2);
      glow.addColorStop(0, "rgba(255,240,200,.9)");
      glow.addColorStop(0.35, working ? "rgba(255,211,106,.47)" : "rgba(255,181,46,.45)");
      glow.addColorStop(1, "rgba(255,181,46,0)");
      context.globalAlpha = 0.9;
      context.fillStyle = glow;
      context.fillRect(0, 0, surface, surface);
      context.strokeStyle = context.fillStyle = orbColor || orbitColor;
      context.shadowColor = orbColor || orbitColor;
      context.shadowBlur = 8;

      rings.forEach((ring, index) => {
        const spin = time * (0.4 + index * 0.17) * (index % 2 ? -1 : 1) + ring[3];
        context.lineWidth = [1.2, 3, 1.6, 3.6, 1.2][index];
        context.setLineDash(index % 2 ? [90, 18, 16, 18] : [36, 10, 4, 10]);
        context.lineDashOffset = -time * 30 * (index + 1);
        context.globalAlpha = 0.85;
        drawArc(ring[0], ring[1], spin, 0, Math.PI * 2, yaw, pitch);
        if (index === 1 || index === 3) {
          context.setLineDash([]);
          context.lineWidth = 6;
          context.globalAlpha = 0.9;
          drawArc(ring[0], ring[1], spin, 0.3, 1.8, yaw, pitch);
          drawArc(ring[0], ring[1], spin, 3.4, 4.9, yaw, pitch);
        }
      });

      context.setLineDash([]);
      context.lineWidth = 1;
      for (let i = 0; i < 28; i += 1) {
        const angle = (i * Math.PI) / 14 + time * 0.2;
        const p0 = project(Math.cos(angle) * 0.62, 0, Math.sin(angle) * 0.62, yaw, pitch);
        const p1 = project(Math.cos(angle) * 1.17, 0, Math.sin(angle) * 1.17, yaw, pitch);
        context.globalAlpha = 0.2 + 0.15 * (i % 3);
        context.beginPath();
        context.moveTo(p0[0], p0[1]);
        context.lineTo(p1[0], p1[1]);
        context.stroke();
      }

      context.shadowBlur = 0;
      spherePoints.forEach(point => {
        const p = project(point[0], point[1], point[2], yaw * 1.8, pitch * 0.6 + 0.2);
        context.globalAlpha = Math.max(0.08, 0.15 + 0.5 * (1 - (p[2] + 1.3) / 2.6));
        context.fillRect(p[0], p[1], 1.7, 1.7);
      });
      dust.forEach(particle => {
        const phase = (time * 0.25 + particle[3]) % 1;
        const distance = 0.5 + phase * 0.9;
        const p = project(particle[0] * distance, particle[1] * distance, particle[2] * distance, yaw, pitch);
        context.globalAlpha = (1 - phase) * 0.9;
        context.fillRect(p[0], p[1], 2.4, 2.4);
      });

      context.globalAlpha = 1;
      context.beginPath();
      context.arc(surface / 2, surface / 2, state === "SPEAKING" ? 7 : 6, 0, Math.PI * 2);
      context.fill();
      context.globalCompositeOperation = "source-over";

      if (!reducedMotion) frameId = window.requestAnimationFrame(draw);
    }

    window.addEventListener("pointermove", trackPointer, { passive: true });
    frameId = window.requestAnimationFrame(draw);
    return () => {
      disposed = true;
      window.cancelAnimationFrame(frameId);
      window.removeEventListener("pointermove", trackPointer);
    };
  }, [working, state]);

  return (
    <div className={`mrai-hud-orb ${working ? "is-working" : ""} state-${String(state).toLowerCase()}`}>
      <canvas
        ref={canvasRef}
        width={SIZE}
        height={SIZE}
        role="img"
        aria-label={`MR AI holographic core, ${state}`}
      />
      <span className="mrai-orb-caption">MR AI CORE</span>
      <span className="mrai-orb-state">{state === "SLEEPING" ? "SLEEP" : state}</span>
    </div>
  );
}
