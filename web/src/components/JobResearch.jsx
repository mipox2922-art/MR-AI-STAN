import { useEffect, useState } from "react";
import {
  getTasks, researchJobs, saveJob, updateJobTracking,
  getJobAutopilot, updateJobAutopilot, saveJobApplicationProfile, runJobAutopilotNow,
} from "../api";

const TRACKING_STATUSES = [
  ["SAVED", "Saved"],
  ["APPLIED", "Applied"],
  ["RESPONSE_RECEIVED", "Response received"],
  ["INTERVIEW", "Interview"],
  ["OFFER", "Offer"],
  ["REJECTED", "Rejected"],
  ["WITHDRAWN", "Withdrawn"],
];

function dateLabel(value) {
  if (!value) return "Date not provided";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date not provided" : date.toLocaleDateString("en-GB", { timeZone: "Africa/Dar_es_Salaam" });
}

function parseTracking(value) {
  if (!value) return {};
  try {
    const parsed = typeof value === "string" ? JSON.parse(value) : value;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function jobUrlFromTask(task) {
  const match = String(task?.description || "").match(/^Job URL:\s*(https:\/\/\S+)/m);
  return match?.[1] || "";
}

function JobAutopilotPanel() {
  const [config, setConfig] = useState({
    enabled: true,
    queries: ["graphic designer", "AI data annotation", "virtual assistant", "remote customer support"],
    interval_hours: 6,
    max_new_jobs: 12,
  });
  const [queryText, setQueryText] = useState(config.queries.join("\n"));
  const [profile, setProfile] = useState({
    full_name: "", email: "", phone: "", location: "", skills: [],
    experience_summary: "", portfolio_url: "", resume_text: "",
  });
  const [skillsText, setSkillsText] = useState("");
  const [metrics, setMetrics] = useState({
    jobs_found: 0, drafts_ready: 0, waiting_for_profile: 0,
    applications_submitted_automatically: 0, failed: 0,
  });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function reload() {
    const data = await getJobAutopilot();
    const nextConfig = { ...config, ...(data.config || {}) };
    const nextProfile = { ...profile, ...(data.profile || {}) };
    setConfig(nextConfig);
    setQueryText((nextConfig.queries || []).join("\n"));
    setProfile(nextProfile);
    const skills = nextProfile.skills || [];
    setSkillsText(Array.isArray(skills) ? skills.join(", ") : String(skills || ""));
    setMetrics(data.metrics || metrics);
    return data;
  }

  useEffect(() => {
    let active = true;
    getJobAutopilot()
      .then(data => {
        if (!active) return;
        const nextConfig = { ...config, ...(data.config || {}) };
        const nextProfile = { ...profile, ...(data.profile || {}) };
        setConfig(nextConfig);
        setQueryText((nextConfig.queries || []).join("\n"));
        setProfile(nextProfile);
        const skills = nextProfile.skills || [];
        setSkillsText(Array.isArray(skills) ? skills.join(", ") : String(skills || ""));
        setMetrics(data.metrics || metrics);
      })
      .catch(err => { if (active) setError(err.message || "Autopilot status could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  function updateProfile(field, value) {
    setProfile(current => ({ ...current, [field]: value }));
  }

  async function saveConfig() {
    setError("");
    const queries = queryText.split(/[\n,;]/).map(item => item.trim()).filter(Boolean);
    if (!queries.length) {
      setError("Weka angalau aina moja ya kazi ya kutafuta.");
      return null;
    }
    const result = await updateJobAutopilot({
      enabled: config.enabled === true,
      queries,
      interval_hours: Number(config.interval_hours) || 6,
      max_new_jobs: Number(config.max_new_jobs) || 12,
    });
    setConfig(current => ({ ...current, ...(result.config || {}), queries }));
    setQueryText(queries.join("\n"));
    return result;
  }

  async function saveSettings() {
    setBusy(true);
    setNotice("");
    setError("");
    try {
      await saveConfig();
      await reload();
      setNotice("Mipangilio ya Job Autopilot imehifadhiwa.");
    } catch (err) {
      setError(err.message || "Mipangilio haikuweza kuhifadhiwa.");
    } finally {
      setBusy(false);
    }
  }

  async function saveProfile() {
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await saveJobApplicationProfile({
        ...profile,
        skills: skillsText.split(/[\n,;]/).map(item => item.trim()).filter(Boolean),
      });
      await reload();
      setNotice(result.message || "Application profile imehifadhiwa.");
    } catch (err) {
      setError(err.message || "Application profile haikuweza kuhifadhiwa.");
    } finally {
      setBusy(false);
    }
  }

  async function runNow() {
    setBusy(true);
    setNotice("");
    setError("");
    try {
      await saveConfig();
      const result = await runJobAutopilotNow();
      await reload();
      setNotice(
        `Run imekamilika: nafasi mpya ${result.new_jobs || 0}, draft zilizoandaliwa ${result.drafts_ready || 0}, zinasubiri profile ${result.waiting_for_profile || 0}. Maombi yaliyotumwa: ${result.applications_submitted || 0}.`
      );
    } catch (err) {
      setError(err.message || "Job Autopilot run imeshindwa.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" style={{ marginBottom: 18 }}>
      <div className="panel-head">
        <div>
          <span className="eyebrow">AGENT CREW · BACKGROUND JOB WORKFLOW</span>
          <h2>Job Autopilot</h2>
          <p>MR AI hutafuta nafasi kwa ratiba, huzuia duplicates, huweka ushahidi na kuandaa drafts kutoka kwenye profile yako.</p>
        </div>
        <span className="badge">{config.enabled ? "AUTOPILOT ON" : "AUTOPILOT OFF"}</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(135px, 1fr))", gap: 10, marginBottom: 16 }}>
        {[
          ["JOBS FOUND", metrics.jobs_found],
          ["DRAFTS READY", metrics.drafts_ready],
          ["WAITING FOR PROFILE", metrics.waiting_for_profile],
          ["AUTO-SUBMITTED", metrics.applications_submitted_automatically],
        ].map(([label, value]) => (
          <div className="service-card" key={label}>
            <strong>{Number(value || 0)}</strong>
            <span>{label}</span>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 2fr) minmax(120px, 1fr) minmax(120px, 1fr)", gap: 10, alignItems: "end" }}>
        <label style={{ display: "grid", gap: 6 }}>
          <span className="eyebrow">ROLES TO SEARCH · ONE PER LINE</span>
          <textarea rows={4} value={queryText} onChange={event => setQueryText(event.target.value)} placeholder={"graphic designer\nAI data annotation\nvirtual assistant"} />
        </label>
        <label style={{ display: "grid", gap: 6 }}>
          <span className="eyebrow">RUN INTERVAL</span>
          <select value={config.interval_hours || 6} onChange={event => setConfig(current => ({ ...current, interval_hours: Number(event.target.value) }))}>
            {[1, 3, 6, 12, 24].map(hours => <option value={hours} key={hours}>Kila saa {hours}</option>)}
          </select>
        </label>
        <label style={{ display: "grid", gap: 6 }}>
          <span className="eyebrow">MAX NEW JOBS / RUN</span>
          <select value={config.max_new_jobs || 12} onChange={event => setConfig(current => ({ ...current, max_new_jobs: Number(event.target.value) }))}>
            {[5, 10, 12, 20, 30].map(count => <option value={count} key={count}>{count}</option>)}
          </select>
        </label>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
        <button className="mini-button" type="button" disabled={busy || loading} onClick={() => setConfig(current => ({ ...current, enabled: !current.enabled }))}>
          {config.enabled ? "TURN AUTOPILOT OFF" : "TURN AUTOPILOT ON"}
        </button>
        <button className="mini-button" type="button" disabled={busy || loading} onClick={saveSettings}>
          {busy ? "WORKING..." : "SAVE AUTOPILOT SETTINGS"}
        </button>
        <button className="primary-button" type="button" disabled={busy || loading} onClick={runNow}>
          {busy ? "RUNNING JOB AGENT..." : "RUN NOW & ENABLE AUTOPILOT"}
        </button>
      </div>

      <details style={{ marginTop: 18 }}>
        <summary style={{ cursor: "pointer", fontWeight: 700 }}>APPLICATION PROFILE · REQUIRED TO PREPARE PERSONALIZED DRAFTS</summary>
        <p style={{ opacity: 0.8 }}>Jaza taarifa zako halisi mara moja. MR AI haitabuni elimu, uzoefu, vyeti au miaka ya kazi ambayo hujaandika.</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10, marginTop: 12 }}>
          <label style={{ display: "grid", gap: 5 }}><span className="eyebrow">FULL NAME</span><input value={profile.full_name || ""} onChange={event => updateProfile("full_name", event.target.value)} autoComplete="name" /></label>
          <label style={{ display: "grid", gap: 5 }}><span className="eyebrow">EMAIL</span><input type="email" value={profile.email || ""} onChange={event => updateProfile("email", event.target.value)} autoComplete="email" /></label>
          <label style={{ display: "grid", gap: 5 }}><span className="eyebrow">PHONE · OPTIONAL</span><input value={profile.phone || ""} onChange={event => updateProfile("phone", event.target.value)} autoComplete="tel" /></label>
          <label style={{ display: "grid", gap: 5 }}><span className="eyebrow">LOCATION</span><input value={profile.location || ""} onChange={event => updateProfile("location", event.target.value)} placeholder="City, country" /></label>
          <label style={{ display: "grid", gap: 5, gridColumn: "1 / -1" }}><span className="eyebrow">SKILLS · SEPARATE WITH COMMAS</span><input value={skillsText} onChange={event => setSkillsText(event.target.value)} placeholder="Graphic design, printing, AI data annotation..." /></label>
          <label style={{ display: "grid", gap: 5, gridColumn: "1 / -1" }}><span className="eyebrow">EXPERIENCE SUMMARY · FACTS ONLY</span><textarea rows={3} value={profile.experience_summary || ""} onChange={event => updateProfile("experience_summary", event.target.value)} placeholder="Describe your real work experience, training and projects." /></label>
          <label style={{ display: "grid", gap: 5, gridColumn: "1 / -1" }}><span className="eyebrow">PORTFOLIO URL · OPTIONAL HTTPS</span><input type="url" value={profile.portfolio_url || ""} onChange={event => updateProfile("portfolio_url", event.target.value)} placeholder="https://..." /></label>
          <label style={{ display: "grid", gap: 5, gridColumn: "1 / -1" }}><span className="eyebrow">CV TEXT · OPTIONAL</span><textarea rows={5} value={profile.resume_text || ""} onChange={event => updateProfile("resume_text", event.target.value)} placeholder="Paste your CV text here, excluding passwords or identity-document numbers." /></label>
        </div>
        <button className="mini-button" type="button" disabled={busy || loading} onClick={saveProfile} style={{ marginTop: 12 }}>
          {busy ? "SAVING..." : "SAVE APPLICATION PROFILE"}
        </button>
      </details>

      {error && <p className="auth-error" role="alert">{error}</p>}
      {notice && <p className="tool-status" role="status" aria-live="polite">{notice}</p>}
      <p style={{ marginTop: 12, opacity: 0.82 }}>
        Ukweli wa sasa: utafutaji na maandalizi yanaweza kufanyika background. Kutuma ombi la mwisho bado hakujafungwa kwenye browser/email execution hand; kwa hiyo MR AI ataonyesha maombi yaliyotumwa = 0 badala ya kudai kuwa ametuma. Ratiba hutegemea scheduler ya backend/GitHub Actions kuwa hai.
      </p>
    </section>
  );
}

export default function JobResearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState("READY");
  const [warning, setWarning] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState({});
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function loadSavedJobs() {
      try {
        const tasks = await getTasks();
        if (!active || !Array.isArray(tasks)) return;
        const restored = {};
        for (const task of tasks) {
          if (task?.agent !== "jobs") continue;
          const url = jobUrlFromTask(task);
          if (!url || restored[url]) continue;
          const tracking = parseTracking(task.result);
          const savedStatus = tracking.status || "SAVED";
          restored[url] = {
            state: "SAVED",
            taskId: task.id,
            selectedStatus: savedStatus,
            evidenceUrl: tracking.evidence_url || "",
            tracking,
          };
        }
        setSaved(restored);
      } catch {
        if (active) setWarning("Saved job history could not be loaded. Refresh the page or check your session.");
      }
    }
    loadSavedJobs();
    return () => { active = false; };
  }, []);

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
    if (saved[job.url]?.state === "SAVING") return;
    setSaved(current => ({ ...current, [job.url]: { ...current[job.url], state: "SAVING" } }));
    setError("");
    try {
      const result = await saveJob(job);
      setSaved(current => ({
        ...current,
        [job.url]: {
          ...current[job.url],
          state: "SAVED",
          taskId: result.task.id,
          selectedStatus: current[job.url]?.selectedStatus || "SAVED",
          evidenceUrl: current[job.url]?.evidenceUrl || "",
          tracking: current[job.url]?.tracking || {},
        },
      }));
      setStatus(`SAVED TO TASKS · #${result.task.id}`);
    } catch (err) {
      setSaved(current => ({ ...current, [job.url]: { ...current[job.url], state: "FAILED" } }));
      setError(err.message || "Could not save this job.");
    }
  }

  function changeTracking(jobUrl, field, value) {
    setSaved(current => ({
      ...current,
      [jobUrl]: { ...current[jobUrl], [field]: value },
    }));
  }

  async function updateTracking(job) {
    const record = saved[job.url];
    if (!record?.taskId || record.state === "TRACKING") return;
    const nextStatus = record.selectedStatus || "SAVED";
    const evidenceUrl = (record.evidenceUrl || "").trim();
    if (evidenceUrl) {
      try {
        if (new URL(evidenceUrl).protocol !== "https:") throw new Error("HTTPS required");
      } catch {
        setError("Link ya ushahidi lazima iwe URL halali inayoanza na https://");
        return;
      }
    }

    setError("");
    setSaved(current => ({ ...current, [job.url]: { ...current[job.url], state: "TRACKING" } }));
    try {
      const result = await updateJobTracking(record.taskId, {
        status: nextStatus,
        evidence_url: evidenceUrl,
        owner_confirmed: nextStatus !== "SAVED",
      });
      setSaved(current => ({
        ...current,
        [job.url]: {
          ...current[job.url],
          state: "SAVED",
          taskId: record.taskId,
          selectedStatus: result.tracking.status,
          evidenceUrl: result.tracking.evidence_url || "",
          tracking: result.tracking,
        },
      }));
      setStatus(`TRACKING SAVED · #${record.taskId} · ${nextStatus}`);
    } catch (err) {
      setSaved(current => ({ ...current, [job.url]: { ...current[job.url], state: "SAVED" } }));
      setError(err.message || "Could not update job tracking.");
    }
  }

  return (
    <>
    <JobAutopilotPanel />
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
      <div className="tool-status" role="status" aria-live="polite">{status}</div>
      {error && <p className="auth-error" role="alert">{error}</p>}
      {warning && <p role="status">{warning}</p>}

      <div className="job-results" style={{ display: "grid", gap: 12, marginTop: 16 }}>
        {results.map(job => {
          const record = saved[job.url];
          const tracking = record?.tracking || {};
          return (
            <article className="agent-card" key={job.url} style={{ alignItems: "start" }}>
              <div className="agent-icon">⌕</div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <strong>{job.title}</strong>
                <span>{job.company} · {job.location}</span>
                <small>{job.source} · {dateLabel(job.published_at)}</small>
                {job.description && <p style={{ margin: "8px 0", overflowWrap: "anywhere" }}>{job.description}</p>}
                {job.tags?.length > 0 && <small>{job.tags.join(" · ")}</small>}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10, alignItems: "center" }}>
                  <a href={job.url} target="_blank" rel="noreferrer">OPEN ORIGINAL POSTING ↗</a>
                  <button
                    className="mini-button"
                    type="button"
                    disabled={record?.state === "SAVING" || Boolean(record?.taskId)}
                    onClick={() => save(job)}
                  >
                    {record?.state === "SAVING" ? "SAVING..." : record?.taskId ? `SAVED · #${record.taskId}` : record?.state === "FAILED" ? "RETRY SAVE" : "SAVE TO TASKS"}
                  </button>
                </div>

                {record?.taskId && (
                  <div style={{ borderTop: "1px solid var(--line)", marginTop: 14, paddingTop: 12, display: "grid", gap: 8 }}>
                    <label htmlFor={`job-status-${record.taskId}`}>APPLICATION TRACKING · TASK #{record.taskId}</label>
                    <select
                      id={`job-status-${record.taskId}`}
                      value={record.selectedStatus || "SAVED"}
                      onChange={event => changeTracking(job.url, "selectedStatus", event.target.value)}
                      disabled={record.state === "TRACKING"}
                    >
                      {TRACKING_STATUSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                    <input
                      type="url"
                      value={record.evidenceUrl || ""}
                      onChange={event => changeTracking(job.url, "evidenceUrl", event.target.value)}
                      placeholder="Optional: link ya ushahidi (HTTPS)"
                      aria-label="Optional evidence URL"
                      disabled={record.state === "TRACKING"}
                    />
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                      <button className="mini-button" type="button" onClick={() => updateTracking(job)} disabled={record.state === "TRACKING"}>
                        {record.state === "TRACKING" ? "SAVING STATUS..." : "SAVE STATUS"}
                      </button>
                      <span className="badge">{tracking.status || "SAVED"}</span>
                      {tracking.owner_confirmed && <small>OWNER CONFIRMED</small>}
                      {tracking.evidence_url && <small>EVIDENCE LINK NOT CHECKED</small>}
                    </div>
                    <small>Hali hii ni taarifa iliyowekwa na mwenye akaunti. MR AI haithibitishi nje kama ombi limetumwa; link ikitolewa haikaguliwi moja kwa moja.</small>
                  </div>
                )}
              </div>
            </article>
          );
        })}
        {!busy && results.length === 0 && (
          <div className="empty">Search for a skill or role to see live listings from the connected public feeds.</div>
        )}
      </div>
      <p style={{ marginTop: 16, opacity: 0.8 }}>
        Usalama: MR AI haiombi wala kutuma maombi yenyewe. Inahifadhi nafasi na link yake; wewe unakagua taarifa na kuamua kutuma ombi.
      </p>
    </section>
    </>
  );
}
