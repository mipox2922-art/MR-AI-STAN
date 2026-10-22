import { useEffect, useState } from "react";
import { createTask, getTasks } from "../api";

function progressValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : null;
}

function parseTaskResult(value) {
  if (!value) return {};
  try {
    const parsed = typeof value === "string" ? JSON.parse(value) : value;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

export default function TaskCenter({ tasks = [], onOpenAgents }) {
  const [items, setItems] = useState(tasks);
  const [title, setTitle] = useState("");
  const [status, setStatus] = useState("TASKS READY");
  const [busy, setBusy] = useState(false);

  useEffect(() => setItems(tasks), [tasks]);

  async function refresh() {
    setBusy(true);
    try {
      const result = await getTasks();
      setItems(Array.isArray(result) ? result : []);
      setStatus("TASKS REFRESHED");
    } catch (error) {
      setStatus("REFRESH FAILED · " + error.message);
    } finally {
      setBusy(false);
    }
  }

  async function submit(event) {
    event.preventDefault();
    const value = title.trim();
    if (!value || busy) return;

    setBusy(true);
    setStatus("CREATING TASK...");
    try {
      await createTask(value);
      setTitle("");
      const result = await getTasks();
      setItems(Array.isArray(result) ? result : []);
      setStatus("TASK CREATED");
    } catch (error) {
      setStatus("CREATE FAILED · " + error.message);
    } finally {
      setBusy(false);
    }
  }

  const ordered = [...items].sort((a, b) => Number(b.id || 0) - Number(a.id || 0));

  return (
    <section className="panel large-panel task-center">
      <div className="panel-head">
        <div>
          <span className="eyebrow">TASK SYSTEM · PERSISTENT BACKEND</span>
          <h2>Mission Tasks</h2>
        </div>
        <div className="panel-head-actions">
          <span className="badge">{items.length} TASKS</span>
          <button className="mini-button" type="button" onClick={refresh} disabled={busy}>REFRESH</button>
          <button className="ghost-button" type="button" onClick={onOpenAgents}>OPEN MISSION PLANNER</button>
        </div>
      </div>

      <form className="task-create-form" onSubmit={submit}>
        <label htmlFor="task-center-title">NEW TASK</label>
        <input
          id="task-center-title"
          value={title}
          onChange={event => setTitle(event.target.value)}
          maxLength={255}
          placeholder="Andika kazi ya kufuatilia..."
          required
        />
        <button type="submit" className="primary-button" disabled={busy || !title.trim()}>
          {busy ? "PLEASE WAIT..." : "CREATE TASK"}
        </button>
      </form>

      <div className="tool-status" role="status" aria-live="polite">{status}</div>
      <div className="task-center-list">
        {ordered.map(task => {
          const progress = progressValue(task.progress);
          const taskStatus = String(task.status || "PENDING").toUpperCase();
          const resultPacket = parseTaskResult(task.result);
          const jobWorkflow = resultPacket.workflow === "JOB_APPLICATION";
          const job = resultPacket.job && typeof resultPacket.job === "object" ? resultPacket.job : {};
          const draft = resultPacket.application_draft && typeof resultPacket.application_draft === "object"
            ? resultPacket.application_draft
            : null;
          return (
            <article className="task-center-row" key={task.id}>
              <div className="task-center-main">
                <strong>{task.title || "Untitled task"}</strong>
                <span>{task.description || "No description provided."}</span>
                <small>#{task.id} · {String(task.agent || "orchestrator").toUpperCase()} · {String(task.priority || "NORMAL").toUpperCase()}</small>
                {jobWorkflow && (
                  <div style={{ marginTop: 12, padding: 12, border: "1px solid var(--line)", borderRadius: 8, display: "grid", gap: 8 }}>
                    <strong>MR AI JOB AGENT · APPLICATION WORKFLOW</strong>
                    <span>{job.company || "Company not listed"} · {job.location || "Location not provided"}</span>
                    {job.url && String(job.url).startsWith("https://") && (
                      <a href={job.url} target="_blank" rel="noreferrer">OPEN ORIGINAL JOB POSTING ↗</a>
                    )}
                    {Number.isFinite(Number(resultPacket.match_score)) && resultPacket.match_score !== null && (
                      <small>SKILL MATCH: {resultPacket.match_score}% · Based on saved profile keywords only</small>
                    )}
                    {draft ? (
                      <details>
                        <summary style={{ cursor: "pointer", fontWeight: 700 }}>OPEN APPLICATION DRAFT · {draft.subject || "Cover letter"}</summary>
                        <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", padding: 10, background: "var(--panel, transparent)", borderRadius: 6 }}>{draft.cover_letter || "No cover letter draft."}</div>
                        <small>{draft.source_note || "Draft only. Check facts before submission."}</small>
                      </details>
                    ) : (
                      <span>Profile bado haijakamilika. Fungua Job Research → Job Autopilot na hifadhi jina, email, skills na muhtasari wa uzoefu.</span>
                    )}
                    <small style={{ fontWeight: 700 }}>APPLICATION SUBMISSION: {resultPacket.submission?.status || "NOT_SUBMITTED"}</small>
                    <small>{resultPacket.submission?.reason || "Hakuna ushahidi wa kuwasilisha ombi bado."}</small>
                  </div>
                )}
              </div>
              <div className="task-center-progress">
                <span className={`task-center-state state-${taskStatus.toLowerCase().replaceAll("_", "-")}`}>{taskStatus}</span>
                <div className="cc-meter"><i style={progress === null ? undefined : { width: `${progress}%` }} /></div>
                <small>{progress === null ? "PROGRESS N/A" : `${progress}% VERIFIED PROGRESS`}</small>
              </div>
            </article>
          );
        })}
        {ordered.length === 0 && (
          <div className="empty">Hakuna tasks bado. Tengeneza task hapo juu au tumia Agents → Mission Planner kwa kazi zinazohitaji agents.</div>
        )}
      </div>
      <p className="notice">Task ya kawaida haiwekwi COMPLETED na dashboard bila ushahidi wa backend. Kazi za agents zinaendeshwa kupitia Mission Planner.</p>
    </section>
  );
}
