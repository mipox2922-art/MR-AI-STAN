import { useEffect, useMemo, useState } from "react";
import { createTask, getTasks, updateTask } from "../api";

const EDITABLE_STATUSES = ["PENDING", "RUNNING", "IN_PROGRESS", "WAITING", "WAITING_FOR_HAND", "WAITING_APPROVAL"];
const TERMINAL_STATUSES = ["COMPLETED", "FAILED", "CANCELLED"];
const PRIORITIES = ["LOW", "NORMAL", "HIGH", "CRITICAL"];

function initialDraft(task) {
  return {
    title: task.title || "",
    priority: PRIORITIES.includes(String(task.priority || "").toUpperCase()) ? String(task.priority).toUpperCase() : "NORMAL",
    status: EDITABLE_STATUSES.includes(String(task.status || "").toUpperCase()) ? String(task.status).toUpperCase() : "PENDING",
    progress: Math.max(0, Math.min(99, Number(task.progress) || 0)),
  };
}

function displayDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export default function TasksPanel() {
  const [tasks, setTasks] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("NORMAL");
  const [agent, setAgent] = useState("orchestrator");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("ALL");
  const [busyId, setBusyId] = useState(null);
  const [creating, setCreating] = useState(false);
  const [status, setStatus] = useState("LOADING TASKS");

  async function loadTasks() {
    try {
      const result = await getTasks();
      const rows = Array.isArray(result) ? result : [];
      setTasks(rows);
      setDrafts(current => {
        const next = { ...current };
        for (const task of rows) {
          if (!next[task.id]) next[task.id] = initialDraft(task);
        }
        for (const id of Object.keys(next)) {
          if (!rows.some(task => String(task.id) === String(id))) delete next[id];
        }
        return next;
      });
      setStatus("TASKS LOADED");
    } catch (error) {
      setStatus("LOAD FAILED · " + error.message);
    }
  }

  useEffect(() => { loadTasks(); }, []);

  const visibleTasks = useMemo(() => tasks.filter(task => {
    const state = String(task.status || "PENDING").toUpperCase();
    const matchesFilter = filter === "ALL" ||
      (filter === "ACTIVE" && !TERMINAL_STATUSES.includes(state)) ||
      (filter === "COMPLETED" && state === "COMPLETED") ||
      (filter === "WAITING" && state.includes("WAITING")) ||
      (filter === "FAILED" && state === "FAILED");
    const haystack = [task.title, task.description, task.agent, task.priority, state].join(" ").toLowerCase();
    return matchesFilter && haystack.includes(query.trim().toLowerCase());
  }), [tasks, filter, query]);

  async function submit(event) {
    event.preventDefault();
    if (!title.trim() || creating) return;
    setCreating(true);
    setStatus("CREATING TASK");
    try {
      await createTask(title.trim(), {
        description: description.trim(),
        priority,
        agent: agent || null,
      });
      setTitle("");
      setDescription("");
      setPriority("NORMAL");
      setAgent("orchestrator");
      await loadTasks();
      setStatus("TASK CREATED");
    } catch (error) {
      setStatus("CREATE FAILED · " + error.message);
    } finally {
      setCreating(false);
    }
  }

  function changeDraft(task, field, value) {
    setDrafts(current => ({
      ...current,
      [task.id]: { ...initialDraft(task), ...current[task.id], [field]: value },
    }));
  }

  async function save(task) {
    const draft = { ...initialDraft(task), ...drafts[task.id] };
    if (!draft.title.trim()) {
      setStatus("TASK TITLE IS REQUIRED");
      return;
    }
    setBusyId(task.id);
    setStatus("SAVING TASK · " + task.id);
    const terminal = TERMINAL_STATUSES.includes(String(task.status || "").toUpperCase());
    const payload = {
      title: draft.title.trim(),
      priority: draft.priority,
      ...(terminal ? {} : { status: draft.status, progress: Number(draft.progress) }),
    };
    try {
      await updateTask(task.id, payload);
      await loadTasks();
      setStatus("TASK SAVED");
    } catch (error) {
      setStatus("SAVE FAILED · " + error.message);
    } finally {
      setBusyId(null);
    }
  }

  const activeCount = tasks.filter(task => !TERMINAL_STATUSES.includes(String(task.status || "").toUpperCase())).length;
  const completedCount = tasks.filter(task => String(task.status || "").toUpperCase() === "COMPLETED").length;

  return (
    <section className="panel large-panel task-manager">
      <div className="panel-head">
        <div><span className="eyebrow">TASK SYSTEM</span><h2>Durable Operations</h2></div>
        <button type="button" className="mini-button" onClick={loadTasks} disabled={busyId !== null || creating}>REFRESH</button>
      </div>

      <div className="task-summary-grid">
        <div><span>TOTAL TASKS</span><strong>{tasks.length}</strong></div>
        <div><span>ACTIVE / WAITING</span><strong>{activeCount}</strong></div>
        <div><span>COMPLETED</span><strong>{completedCount}</strong></div>
      </div>

      <form className="task-create-form" onSubmit={submit}>
        <label>TASK TITLE
          <input value={title} onChange={event => setTitle(event.target.value)} maxLength={255} required placeholder="Kazi mpya ya MR AI..." />
        </label>
        <label>DESCRIPTION
          <textarea value={description} onChange={event => setDescription(event.target.value)} maxLength={12000} rows={2} placeholder="Maelezo ya hiari ya kazi" />
        </label>
        <div className="task-create-row">
          <label>PRIORITY
            <select value={priority} onChange={event => setPriority(event.target.value)}>
              {PRIORITIES.map(value => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <label>ASSIGNED AGENT
            <select value={agent} onChange={event => setAgent(event.target.value)}>
              <option value="orchestrator">MR AI Orchestrator</option>
              <option value="research">Research Agent</option>
              <option value="browser">Browser Agent</option>
              <option value="jobs">Job Research Agent</option>
              <option value="coding">Coding Agent</option>
              <option value="creative">Creative Studio Agent</option>
              <option value="device">Device Lab Agent</option>
              <option value="security">Security Agent</option>
              <option value="memory">Memory Agent</option>
              <option value="scheduler">Scheduler Agent</option>
              <option value="">Unassigned</option>
            </select>
          </label>
          <button type="submit" className="primary-button" disabled={creating || !title.trim()}>{creating ? "CREATING..." : "CREATE TASK"}</button>
        </div>
      </form>

      <div className="task-list-toolbar">
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search tasks..." aria-label="Search tasks" />
        <select value={filter} onChange={event => setFilter(event.target.value)} aria-label="Filter tasks">
          <option value="ALL">ALL TASKS</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="WAITING">WAITING</option>
          <option value="COMPLETED">COMPLETED</option>
          <option value="FAILED">FAILED</option>
        </select>
      </div>

      <div className="tool-status" role="status" aria-live="polite">{status}</div>

      <div className="managed-task-list">
        {visibleTasks.map(task => {
          const terminal = TERMINAL_STATUSES.includes(String(task.status || "").toUpperCase());
          const draft = { ...initialDraft(task), ...drafts[task.id] };
          const progress = Number.isFinite(Number(task.progress)) ? Math.max(0, Math.min(100, Number(task.progress))) : 0;
          return (
            <article className="managed-task-card" key={task.id}>
              <div className="managed-task-head">
                <span className="task-id">TASK #{task.id}</span>
                <span className={"task-state state-" + String(task.status || "PENDING").toLowerCase().replaceAll("_", "-")}>{String(task.status || "PENDING").replaceAll("_", " ")}</span>
              </div>
              <label>TITLE
                <input value={draft.title} onChange={event => changeDraft(task, "title", event.target.value)} aria-label={"Task title " + task.id} maxLength={255} />
              </label>
              <div className="managed-task-meta">
                <span>AGENT <strong>{task.agent || "UNASSIGNED"}</strong></span>
                <span>UPDATED <strong>{displayDate(task.updated_at || task.created_at)}</strong></span>
              </div>
              {task.description && <p className="managed-task-description">{task.description}</p>}
              <div className="task-edit-row">
                <label>PRIORITY
                  <select value={draft.priority} onChange={event => changeDraft(task, "priority", event.target.value)} aria-label={"Task priority " + task.id}>
                    {PRIORITIES.map(value => <option key={value} value={value}>{value}</option>)}
                  </select>
                </label>
                <label>STATUS
                  <select value={terminal ? String(task.status).toUpperCase() : draft.status} disabled={terminal} onChange={event => changeDraft(task, "status", event.target.value)} aria-label={"Task status " + task.id}>
                    {terminal
                      ? <option value={String(task.status).toUpperCase()}>{String(task.status).toUpperCase()}</option>
                      : EDITABLE_STATUSES.map(value => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}
                  </select>
                </label>
                <label>PROGRESS %
                  <input type="number" min="0" max="99" step="1" value={terminal ? progress : draft.progress} disabled={terminal} onChange={event => changeDraft(task, "progress", event.target.value)} aria-label={"Task progress " + task.id} />
                </label>
                <button type="button" className="mini-button" onClick={() => save(task)} disabled={busyId !== null || creating}>{busyId === task.id ? "SAVING..." : "SAVE"}</button>
              </div>
              <div className="task-progress-track"><i style={{ width: progress + "%" }} /></div>
              {task.error && <p className="task-error">{task.error}</p>}
              {task.result && <details><summary>VIEW RESULT / EVIDENCE</summary><pre>{String(task.result)}</pre></details>}
              <small className="task-completion-note">Completion is controlled by verified execution evidence. Manual edits cannot mark a task completed.</small>
            </article>
          );
        })}
        {visibleTasks.length === 0 && <div className="empty">{tasks.length ? "No tasks match this filter." : "No tasks yet. Create the first task above."}</div>}
      </div>
    </section>
  );
}
