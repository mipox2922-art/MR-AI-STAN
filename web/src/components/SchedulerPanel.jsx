import { useEffect, useMemo, useState } from "react";
import { createSchedule, deleteSchedule, getSchedules, runScheduleNow, updateSchedule } from "../api";

function displayDate(value) {
  if (!value) return "N/A";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "N/A";
  return date.toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function toIso(localValue) {
  if (!localValue) return "";
  const date = new Date(localValue);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

export default function SchedulerPanel() {
  const [jobs, setJobs] = useState([]);
  const [title, setTitle] = useState("");
  const [command, setCommand] = useState("");
  const [runAt, setRunAt] = useState("");
  const [interval, setInterval] = useState("");
  const [status, setStatus] = useState("READY");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setJobs(await getSchedules());
      setStatus("SCHEDULES LOADED");
    } catch (error) {
      setStatus("ERROR / " + error.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const activeCount = useMemo(
    () => jobs.filter(job => job.status === "ACTIVE").length,
    [jobs]
  );

  async function submit(event) {
    event.preventDefault();
    const iso = toIso(runAt);

    if (!title.trim() || !command.trim() || !iso) {
      setStatus("TITLE, COMMAND AND RUN TIME ARE REQUIRED");
      return;
    }

    setBusy(true);
    setStatus("CREATING...");
    try {
      await createSchedule({
        title: title.trim(),
        command: command.trim(),
        run_at: iso,
        interval_minutes: interval ? Number(interval) : null,
      });
      setTitle("");
      setCommand("");
      setRunAt("");
      setInterval("");
      setStatus("SCHEDULE CREATED");
      await load();
    } catch (error) {
      setStatus("CREATE FAILED / " + error.message);
    } finally {
      setBusy(false);
    }
  }

  async function toggle(job) {
    setStatus("UPDATING...");
    try {
      await updateSchedule(job.id, {
        status: job.status === "ACTIVE" ? "PAUSED" : "ACTIVE",
      });
      await load();
    } catch (error) {
      setStatus("UPDATE FAILED / " + error.message);
    }
  }

  async function runNow(job) {
    setStatus("QUEUING NOW...");
    try {
      await runScheduleNow(job.id);
      setStatus("SCHEDULE QUEUED");
      await load();
    } catch (error) {
      setStatus("RUN NOW FAILED / " + error.message);
    }
  }

  async function remove(job) {
    setStatus("DELETING...");
    try {
      await deleteSchedule(job.id);
      await load();
    } catch (error) {
      setStatus("DELETE FAILED / " + error.message);
    }
  }

  return (
    <section className="panel large-panel scheduler-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">SCHEDULER AGENT</span>
          <h2>Proactive Operations</h2>
        </div>
        <span className="badge">{activeCount} ACTIVE</span>
      </div>

      <form className="scheduler-form" onSubmit={submit}>
        <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Schedule title" />
        <input value={command} onChange={e => setCommand(e.target.value)} placeholder="Command to queue when due" />
        <label>
          RUN AT
          <input type="datetime-local" value={runAt} onChange={e => setRunAt(e.target.value)} />
        </label>
        <label>
          EVERY MINUTES
          <input type="number" min="1" step="1" value={interval} onChange={e => setInterval(e.target.value)} placeholder="One-shot if empty" />
        </label>
        <button className="primary-button" disabled={busy}>CREATE SCHEDULE</button>
      </form>

      <div className="tool-status">{status}</div>

      <div className="schedule-list">
        {jobs.map(job => (
          <article className="schedule-row" key={job.id}>
            <div className="schedule-main">
              <strong>{job.title}</strong>
              <span>{job.command}</span>
              <small>
                NEXT: {displayDate(job.next_run_at)} ·{" "}
                {job.interval_minutes ? `RECURS ${job.interval_minutes}m` : "ONE-SHOT"}
              </small>
            </div>
            <span className={`schedule-state schedule-${job.status.toLowerCase()}`}>{job.status}</span>
            <div className="schedule-actions">
              {job.status !== "COMPLETED" && (
                <button className="mini-button" onClick={() => toggle(job)}>
                  {job.status === "ACTIVE" ? "PAUSE" : "RESUME"}
                </button>
              )}
              <button className="mini-button" onClick={() => runNow(job)}>RUN NOW</button>
              <button className="ghost-button" onClick={() => remove(job)}>DELETE</button>
            </div>
          </article>
        ))}
        {jobs.length === 0 && <div className="empty">No schedules configured yet.</div>}
      </div>
    </section>
  );
}
