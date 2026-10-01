import { useState } from "react";
import { browserClick, browserNavigate, browserScroll, browserType, getCurrentPage } from "../api";

export default function BrowserHands() {
  const [url, setUrl] = useState("");
  const [selector, setSelector] = useState("");
  const [value, setValue] = useState("");
  const [page, setPage] = useState(null);
  const [message, setMessage] = useState("READY");

  async function run(label, fn) {
    setMessage(label + "...");
    try {
      const result = await fn();
      setMessage(label + " ✓");
      if (result?.text) setPage(result);
    } catch (error) {
      setMessage(label + " ✕ " + error.message);
    }
  }

  return (
    <section className="tool-panel">
      <div className="panel-title">BROWSER HANDS</div>
      <div className="tool-grid">
        <button onClick={() => run("READ PAGE", getCurrentPage)}>READ PAGE</button>
        <button onClick={() => run("SCROLL", () => browserScroll(700))}>SCROLL</button>
      </div>
      <div className="tool-row">
        <input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://..." />
        <button onClick={() => run("NAVIGATE", () => browserNavigate(url))}>OPEN</button>
      </div>
      <div className="tool-row">
        <input value={selector} onChange={e => setSelector(e.target.value)} placeholder="CSS selector" />
        <button onClick={() => run("CLICK", () => browserClick(selector))}>CLICK</button>
      </div>
      <div className="tool-row">
        <input value={value} onChange={e => setValue(e.target.value)} placeholder="Text" />
        <button onClick={() => run("TYPE", () => browserType(selector, value))}>TYPE</button>
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
