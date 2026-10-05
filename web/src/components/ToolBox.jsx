import { useEffect, useMemo, useState } from "react";
import { getTools, searchToolWeb } from "../api";

function statusClass(status) {
  return String(status).toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

export default function ToolBox() {
  const [registry, setRegistry] = useState(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searchStatus, setSearchStatus] = useState("READY");

  useEffect(() => {
    getTools().then(setRegistry).catch(() => setRegistry({ tools: [] }));
  }, []);

  const tools = registry?.tools || [];
  const categories = useMemo(
    () => Array.from(new Set(tools.map(tool => tool.category))).sort(),
    [tools]
  );

  async function search() {
    if (!query.trim()) return;
    setSearchStatus("SEARCHING");
    try {
      const data = await searchToolWeb(query.trim());
      setResults(data.results || []);
      setSearchStatus(data.status || "UNKNOWN");
    } catch (error) {
      setResults([]);
      setSearchStatus(error.message);
    }
  }

  return (
    <section className="panel large-panel toolbox-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">TOOL INTELLIGENCE</span>
          <h2>MR AI Toolbox</h2>
        </div>
        <span className="badge">{registry?.total || tools.length} TOOLS</span>
      </div>

      <div className="tool-summary">
        <div><span>READY</span><strong>{registry?.ready ?? "N/A"}</strong></div>
        <div><span>OPTIONAL</span><strong>{registry?.optional ?? "N/A"}</strong></div>
        <div><span>NOT CONNECTED</span><strong>{registry?.not_connected ?? "N/A"}</strong></div>
      </div>

      {categories.map(category => (
        <div className="tool-category" key={category}>
          <div className="panel-title">{category}</div>
          <div className="tool-registry-grid">
            {tools.filter(tool => tool.category === category).map(tool => (
              <article className="tool-registry-card" key={tool.id}>
                <div className="tool-card-head">
                  <strong>{tool.name}</strong>
                  <span className={`tool-state ${statusClass(tool.status)}`}>{tool.status}</span>
                </div>
                <p>{tool.description}</p>
                <small>
                  {tool.mode || "SYSTEM"} · {tool.free ? "FREE/OPEN" : "ACCOUNT/API MAY APPLY"}
                  {tool.binary ? ` · ${tool.binary}` : ""}
                </small>
              </article>
            ))}
          </div>
        </div>
      ))}

      <div className="tool-search">
        <div className="panel-title">SELF-HOSTED WEB SEARCH</div>
        <div className="tool-search-row">
          <input
            value={query}
            onChange={event => setQuery(event.target.value)}
            onKeyDown={event => {
              if (event.key === "Enter") search();
            }}
            placeholder="Search through configured SearXNG..."
          />
          <button className="primary-button" onClick={search}>SEARCH</button>
        </div>
        <div className="tool-status">{searchStatus}</div>

        {results.length > 0 && (
          <div className="search-results">
            {results.map((result, index) => (
              <article className="search-result" key={result.url || index}>
                <a href={result.url} target="_blank" rel="noreferrer">
                  {result.title || result.url}
                </a>
                <span>{result.content || "No excerpt returned."}</span>
                <small>{result.engine || "SearXNG"}</small>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
