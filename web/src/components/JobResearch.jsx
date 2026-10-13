import { useState } from "react";
import { researchJobs, saveJob } from "../api";

function dateLabel(value) {
  if (!value) return "Date not provided";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date not provided" : date.toLocaleDateString();
}

export default function JobResearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState("READY");
  const [warning, setWarning] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState({});
  const [error, setError] = useState("");

  async function search(event) {
    event.preventDefault();
    if (query.trim().length < 2) {
      setError("Andika ujuzi au aina ya kazi, angalau herufi mbili.");
      return;
    }
    setBusy(true);
    setError("");
    setWarning("");
    setStatus("SEARCHING PUBLIC JOB FEEDS...");
    try {
      const data = await researchJobs(query.trim(), 30);
      setResults(Array.isArray(data.results) ? data.results : []);
      setWarning(data.source_warnings?.length
        ? "Chanzo kimoja hakikupatikana. Matokeo yaliyopo bado yanaonyeshwa."
        : "");
      setStatus(data.count ? `${data.count} JOBS FOUND · ${(data.sources || []).join(" + ")}` : "NO MATCHING JOBS");
    } catch (err) {
      setResults([]);
      setStatus("SEARCH FAILED");
      setError(err.message || "Job sources are unavailable.");
    } finally {
      setBusy(false);
    }
  }

  async function save(job) {
    setSaved(current => ({ ...current, [job.url]: "SAVING" }));
    try {
      const result = await saveJob(job);
      setSaved(current => ({ ...current, [job.url]: "SAVED" }));
      setStatus(`SAVED TO TASKS · #${result.task.id}`);
    } catch (err) {
      setSaved(current => ({ ...current, [job.url]: "FAILED" }));
      setError(err.message || "Could not save this job.");
    }
  }

  return (
    <section className="panel large-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">JOBS AGENT · LIVE PUBLIC SOURCES</span>
          <h2>Job Research</h2>
          <p>Agent inatafuta nafasi za remote kwenye RemoteOK na Remotive. Hifadhi nafasi nzuri kwenye Tasks ili ufuatilie maombi.</p>
        </div>
        <span className="badge">{results.length} RESULTS</span>
      </div>

      <form className="planner-row" onSubmit={search}>
        <input
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Mfano: Python developer, React, customer support"
          aria-label="Job search terms"
          minLength={2}
          required
        />
        <button className="primary-button" disabled={busy}>{busy ? "SEARCHING..." : "SEARCH JOBS"}</button>
      </form>
      <div className="tool-status" role="status">{status}</div>
      {error && <p className="auth-error" role="alert">{error}</p>}
      {warning && <p>{warning}</p>}

      <div className="job-results" style={{ display: "grid", gap: 12, marginTop: 16 }}>
        {results.map(job => (
          <article className="agent-card" key={job.url} style={{ alignItems: "start" }}>
            <div className="agent-icon">⌕</div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <strong>{job.title}</strong>
              <span>{job.company} · {job.location}</span>
              <small>{job.source} · {dateLabel(job.published_at)}</small>
              {job.description && <p style={{ margin: "8px 0", overflowWrap: "anywhere" }}>{job.description}</p>}
              {job.tags?.length > 0 && <small>{job.tags.join(" · ")}</small>}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
                <a href={job.url} target="_blank" rel="noreferrer">OPEN ORIGINAL POSTING ↗</a>
                <button
                  className="mini-button"
                  type="button"
                  disabled={saved[job.url] === "SAVED" || saved[job.url] === "SAVING"}
                  onClick={() => save(job)}
                >
                  {saved[job.url] === "SAVING" ? "SAVING..." : saved[job.url] === "SAVED" ? "SAVED TO TASKS" : "SAVE TO TASKS"}
                </button>
              </div>
            </div>
          </article>
        ))}
        {!busy && results.length === 0 && (
          <div className="empty">Search for a skill or role to see live listings from the connected public feeds.</div>
        )}
      </div>
      <p style={{ marginTop: 16, opacity: 0.8 }}>
        Usalama: MR AI haiombi wala kutuma maombi yenyewe. Inahifadhi nafasi na link yake; wewe unakagua taarifa na kuamua kutuma ombi.
      </p>
    </section>
  );
}
