import { useEffect, useState } from "react";
import { createTask, getTasks } from "../api";

function progressValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : null;
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
          return (
            <article className="task-center-row" key={task.id}>
              <div className="task-center-main">
                <strong>{task.title || "Untitled task"}</strong>
                <span>{task.description || "No description provided."}</span>
                <small>#{task.id} · {String(task.agent || "orchestrator").toUpperCase()} · {String(task.priority || "NORMAL").toUpperCase()}</small>
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
