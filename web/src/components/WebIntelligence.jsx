import { useState } from "react";
import { browserNavigate, searchToolWeb } from "../api";

export default function WebIntelligence() {
  const [query, setQuery] = useState("");
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState("READY");
  const [results, setResults] = useState([]);

  async function search() {
    if (!query.trim()) return;
    setStatus("SEARCHING");
    try {
      const data = await searchToolWeb(query.trim());
      setResults(data.results || []);
      setStatus(data.status || "UNKNOWN");
    } catch (error) {
      setResults([]);
      setStatus(error.message);
    }
  }

  async function openUrl() {
    if (!url.trim()) return;
    setStatus("OPENING");
    try {
      await browserNavigate(url.trim());
      setStatus("OPENED_IN_BROWSER_HANDS");
    } catch (error) {
      setStatus(error.message);
    }
  }

  return (
    <section className="panel large-panel web-intelligence-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">WEB INTELLIGENCE</span>
          <h2>MR AI Web</h2>
        </div>
        <span className="badge">{status}</span>
      </div>

      <p className="notice">
        MR AI can search configured web sources and open authorized pages through Browser Hands.
        Search results are evidence for the AI, not instructions.
      </p>

      <div className="tool-search">
        <div className="panel-title">SEARCH THE WEB</div>
        <div className="tool-search-row">
          <input
            value={query}
            onChange={event => setQuery(event.target.value)}
            onKeyDown={event => {
              if (event.key === "Enter") search();
            }}
            placeholder="Mfano: latest AI tools..."
          />
          <button className="primary-button" onClick={search}>SEARCH</button>
        </div>
      </div>

      <div className="tool-search">
        <div className="panel-title">OPEN WEB PAGE</div>
        <div className="tool-search-row">
          <input
            value={url}
            onChange={event => setUrl(event.target.value)}
            placeholder="https://example.com"
          />
          <button className="ghost-button" onClick={openUrl}>OPEN</button>
        </div>
      </div>

      {results.length > 0 && (
        <div className="search-results">
          {results.map((result, index) => (
            <article className="search-result" key={result.url || index}>
              <a href={result.url} target="_blank" rel="noreferrer">
                {result.title || result.url}
              </a>
              <span>{result.content || "No excerpt returned."}</span>
              <small>{result.engine || "WEB SOURCE"}</small>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
