import { useState } from "react";
import {
  browserClick,
  browserDrag,
  browserNavigate,
  browserScroll,
  browserType,
  getCurrentPage
} from "../api";

export default function BrowserHands() {
  const [url, setUrl] = useState("");
  const [selector, setSelector] = useState("");
  const [value, setValue] = useState("");
  const [dx, setDx] = useState("120");
  const [dy, setDy] = useState("0");
  const [page, setPage] = useState(null);
  const [message, setMessage] = useState("READY");

  async function run(label, fn) {
    setMessage(label + "...");
    try {
      const result = await fn();
      setMessage(label + " ✓ VERIFIED");
      if (result?.text) setPage(result);
    } catch (error) {
      setMessage(label + " ✕ " + error.message);
    }
  }

  return (
    <section className="tool-panel">
      <div className="panel-title">BROWSER HANDS — AUTHORIZED PAGE CONTROL</div>

      <div className="tool-grid">
        <button onClick={() => run("READ PAGE", getCurrentPage)}>READ PAGE</button>
        <button onClick={() => run("SCROLL", () => browserScroll(700))}>SCROLL DOWN</button>
        <button onClick={() => run("SCROLL", () => browserScroll(-700))}>SCROLL UP</button>
      </div>

      <div className="tool-row">
        <input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://..." />
        <button onClick={() => run("NAVIGATE", () => browserNavigate(url))}>OPEN</button>
      </div>

      <div className="tool-row">
        <input value={selector} onChange={e => setSelector(e.target.value)} placeholder="CSS selector, e.g. button[type=submit]" />
        <button onClick={() => run("CLICK", () => browserClick(selector))}>CLICK</button>
      </div>

      <div className="tool-row">
        <input value={value} onChange={e => setValue(e.target.value)} placeholder="Text to type" />
        <button onClick={() => run("TYPE", () => browserType(selector, value))}>TYPE</button>
      </div>

      <div className="tool-row">
        <input value={dx} onChange={e => setDx(e.target.value)} inputMode="numeric" placeholder="dx" />
        <input value={dy} onChange={e => setDy(e.target.value)} inputMode="numeric" placeholder="dy" />
        <button onClick={() => run("DRAG", () => browserDrag(selector, Number(dx), Number(dy)))}>DRAG</button>
      </div>

      <div className="tool-status">{message}</div>

      {page && (
        <div className="page-preview">
          <strong>{page.title}</strong>
          <span>{page.url}</span>
          <pre>{page.text}</pre>
        </div>
      )}
    </section>
  );
}
