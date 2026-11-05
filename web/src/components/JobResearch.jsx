import { useEffect, useMemo, useState } from "react";
import {
  getTasks,
  researchJobs,
  saveJob,
  updateJobTracking,
  getJobAutopilot,
  updateJobAutopilot,
  saveJobApplicationProfile,
  importJobApplicationProfileFromMemory,
  runJobAutopilotNow,
} from "../api";

const TRACKING_STATUSES = [
  ["SAVED", "Imehifadhiwa"],
  ["APPLIED", "Nimetuma ombi"],
  ["RESPONSE_RECEIVED", "Nimepata majibu"],
  ["INTERVIEW", "Mahojiano"],
  ["OFFER", "Nimepata ofa"],
  ["REJECTED", "Nimekataliwa"],
  ["WITHDRAWN", "Nimejiondoa"],
];

const DEFAULT_CONFIG = {
  enabled: true,
  queries: [
    "graphic designer",
    "AI data annotation",
    "virtual assistant",
    "remote customer support",
  ],
  interval_hours: 6,
  max_new_jobs: 12,
};

const EMPTY_PROFILE = {
  full_name: "",
  email: "",
  phone: "",
  location: "",
  skills: [],
  experience_summary: "",
  portfolio_url: "",
  resume_text: "",
};

const LOCAL_JOB_SOURCES = [
  {
    title: "NipeDili",
    type: "KAZI NDOGO · DILI ZA KARIBU",
    description: "Tafuta kazi za muda, vibarua, huduma na dili za moja kwa moja Tanzania.",
    url: "https://nipedilitz.com/",
    action: "FUNGUA DILI",
  },
  {
    title: "Work.tz",
    type: "NAFASI ZA KAZI TANZANIA",
    description: "Angalia matangazo ya waajiri na fuata link ya tangazo la asili.",
    url: "https://work.tz/sw/jobs/",
    action: "TAFUTA KAZI",
  },
  {
    title: "Ajira Portal",
    type: "AJIRA ZA SERIKALI",
    description: "Matangazo na usimamizi wa maombi ya ajira za umma.",
    url: "https://ajira.go.tz/recruitment_management",
    action: "FUNGUA PORTAL",
  },
];

const QUICK_SEARCHES = [
  "graphic designer",
  "virtual assistant",
  "data annotation",
  "transcription",
  "social media assistant",
  "customer support",
  "website updates",
  "part-time freelance",
];

function dateLabel(value) {
  if (!value) return "Tarehe haijawekwa";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Tarehe haijawekwa"
    : date.toLocaleDateString("en-GB", { timeZone: "Africa/Dar_es_Salaam" });
}

function parsePacket(value) {
  if (!value) return {};
  try {
    const parsed = typeof value === "string" ? JSON.parse(value) : value;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function jobUrlFromTask(task) {
  const packet = parsePacket(task?.result);
  const packetUrl = packet?.job?.url || "";
  if (String(packetUrl).startsWith("https://")) return packetUrl;
  const match = String(task?.description || "").match(/^Job URL:\s*(https:\/\/\S+)/m);
  return match?.[1] || "";
}

function trackingFromTask(task) {
  const packet = parsePacket(task?.result);
  return packet.workflow === "JOB_APPLICATION"
    ? (packet.tracking || {})
    : packet;
}

function isApplicationTask(task) {
  const packet = parsePacket(task?.result);
  return task?.agent === "jobs" && (
    packet.workflow === "JOB_APPLICATION" ||
    (task?.source === "autopilot" && Boolean(packet.job?.url))
  );
}

function statusLabel(status) {
  const labels = {
    READY_FOR_REVIEW: "DRAFT TAYARI",
    WAITING_FOR_PROFILE: "INASUBIRI CV",
    NOT_ELIGIBLE: "HAIKUBALI TANZANIA",
    WAITING_FOR_ELIGIBILITY: "THIBITISHA LOCATION",
    COMPLETED: "IMEKAMILIKA",
    FAILED: "IMESHINDWA",
    ERROR: "KUNA HITILAFU",
    SAVED: "IMEHIFADHIWA",
    APPLIED: "ULIRIPOTI KUWA UMETUMA",
    RESPONSE_RECEIVED: "MAJIBU YAMEPOKELEWA",
    INTERVIEW: "MAHOJIANO",
    OFFER: "OFA IMEPOKELEWA",
    REJECTED: "IMEKATALIWA",
    WITHDRAWN: "UMEJIONDOA",
  };
  const key = String(status || "SAVED").toUpperCase();
  return labels[key] || key.replaceAll("_", " ");
}

function JobMetric({ label, value, tone }) {
  return (
    <div className={"job-metric" + (tone ? " " + tone : "")}>
      <strong>{Number(value || 0).toLocaleString()}</strong>
      <span>{label}</span>
    </div>
  );
}

export default function JobResearch() {
  const [config, setConfig] = useState(DEFAULT_CONFIG);
  const [queryText, setQueryText] = useState(DEFAULT_CONFIG.queries.join("\n"));
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [skillsText, setSkillsText] = useState("");
  const [profileReady, setProfileReady] = useState(false);
  const [metrics, setMetrics] = useState({
    jobs_found: 0,
    drafts_ready: 0,
    waiting_for_profile: 0,
    applications_submitted_automatically: 0,
    failed: 0,
  });
  const [applicationTasks, setApplicationTasks] = useState([]);
  const [applicationTracking, setApplicationTracking] = useState({});
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [saved, setSaved] = useState({});
  const [status, setStatus] = useState("MR AI iko tayari kutafuta kazi.");
  const [notice, setNotice] = useState("");
  const [warning, setWarning] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");

  function hydrateTasks(tasks) {
    const rows = Array.isArray(tasks) ? tasks : [];
    const restored = {};
    const applications = [];
    for (const task of rows) {
      if (task?.agent !== "jobs") continue;
      const url = jobUrlFromTask(task);
      const tracking = trackingFromTask(task);
      if (url && !restored[url]) {
        const savedStatus = TRACKING_STATUSES.some(([value]) => value === tracking.status)
          ? tracking.status
          : "SAVED";
        restored[url] = {
          state: "SAVED",
          taskId: task.id,
          selectedStatus: savedStatus,
          evidenceUrl: tracking.evidence_url || "",
          tracking,
        };
      }
      if (isApplicationTask(task)) applications.push(task);
    }
    applications.sort((a, b) => Number(b.id || 0) - Number(a.id || 0));
    setSaved(restored);
    setApplicationTasks(applications);
    setApplicationTracking(current => {
      const next = { ...current };
      for (const task of applications) {
        const tracking = trackingFromTask(task);
        if (!next[task.id]) {
          next[task.id] = {
            status: tracking.status || "SAVED",
            evidence_url: tracking.evidence_url || "",
          };
        }
      }
      return next;
    });
  }

  async function reloadWorkspace() {
    const [profileResult, tasksResult] = await Promise.allSettled([
      getJobAutopilot(),
      getTasks(),
    ]);
    if (profileResult.status !== "fulfilled") throw profileResult.reason;
    const data = profileResult.value;
    const tasks = tasksResult.status === "fulfilled" ? tasksResult.value : [];
    const nextConfig = { ...DEFAULT_CONFIG, ...(data?.config || {}) };
    const nextProfile = { ...EMPTY_PROFILE, ...(data?.profile || {}) };
    setConfig(nextConfig);
    setQueryText((nextConfig.queries || []).join("\n"));
    setProfile(nextProfile);
    const skills = nextProfile.skills || [];
    setSkillsText(Array.isArray(skills) ? skills.join(", ") : String(skills || ""));
    setProfileReady(data?.profile_ready === true);
    setMetrics(data?.metrics || {
      jobs_found: 0,
      drafts_ready: 0,
      waiting_for_profile: 0,
      applications_submitted_automatically: 0,
      failed: 0,
    });
    hydrateTasks(tasks);
    setWarning(tasksResult.status === "fulfilled" ? "" : "CV imepakiwa, lakini history ya Tasks haikupatikana.");
    return { data, tasks };
  }

  useEffect(() => {
    let active = true;
    Promise.allSettled([getJobAutopilot(), getTasks()])
      .then(([profileResult, tasksResult]) => {
        if (!active) return;
        if (profileResult.status !== "fulfilled") throw profileResult.reason;
        const data = profileResult.value;
        const nextConfig = { ...DEFAULT_CONFIG, ...(data?.config || {}) };
        const nextProfile = { ...EMPTY_PROFILE, ...(data?.profile || {}) };
        setConfig(nextConfig);
        setQueryText((nextConfig.queries || []).join("\n"));
        setProfile(nextProfile);
        const skills = nextProfile.skills || [];
        setSkillsText(Array.isArray(skills) ? skills.join(", ") : String(skills || ""));
        setProfileReady(data?.profile_ready === true);
        setMetrics(data?.metrics || {});
        hydrateTasks(tasksResult.status === "fulfilled" ? tasksResult.value : []);
        if (tasksResult.status !== "fulfilled") {
          setWarning("CV imepakiwa, lakini history ya Tasks haikupatikana.");
        }
      })
      .catch(err => {
        if (active) setError(err.message || "Job workspace haikuweza kupakia.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  const applicationRows = useMemo(() => applicationTasks.map(task => {
    const packet = parsePacket(task.result);
    return { task, packet, job: packet.job || {}, draft: packet.application_draft || null };
  }), [applicationTasks]);

  function updateProfile(field, value) {
    setProfile(current => ({ ...current, [field]: value }));
  }

  async function saveProfile() {
    setBusy("PROFILE");
    setNotice("");
    setError("");
    try {
      const payload = {
        ...profile,
        skills: skillsText.split(/[\n,;]/).map(item => item.trim()).filter(Boolean),
      };
      const result = await saveJobApplicationProfile(payload);
      const refreshed = await reloadWorkspace();
      setNotice(
        (result.message || "CV na profile zimehifadhiwa.") +
        (Number(result.drafts_refreshed || 0) ? " Draft " + result.drafts_refreshed + " zimehuishwa." : "")
      );
      if (refreshed.data?.profile_ready) setProfileReady(true);
    } catch (err) {
      setError(err.message || "CV haikuweza kuhifadhiwa.");
    } finally {
      setBusy("");
    }
  }

  async function importProfileFromMemory() {
    setBusy("IMPORT");
    setNotice("");
    setError("");
    try {
      const result = await importJobApplicationProfileFromMemory();
      await reloadWorkspace();
      const fields = Array.isArray(result.imported_fields) ? result.imported_fields : [];
      setNotice(
        result.status === "IMPORTED"
          ? (result.message || "CV imeingizwa kutoka MR AI Memory.") +
            (fields.length ? " Sehemu: " + fields.join(", ") + "." : "")
          : (result.message || "Hakuna CV iliyopatikana kwenye Memory.")
      );
    } catch (err) {
      setError(err.message || "CV haikuweza kuhamishwa kutoka Memory.");
    } finally {
      setBusy("");
    }
  }

  async function importTextFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    setNotice("");
    const extension = file.name.split(".").pop().toLowerCase();
    if (!["txt", "md", "text"].includes(extension)) {
      setError("Kwa sasa chagua CV ya .txt au .md. PDF/DOCX haijawashwa kama import ya moja kwa moja.");
      event.target.value = "";
      return;
    }
    try {
      const text = await file.text();
      updateProfile("resume_text", text.slice(0, 6000));
      setNotice("CV imesomwa. Bonyeza HIFADHI CV & PROFILE ili kuihifadhi kwenye akaunti yako.");
    } catch {
      setError("Faili ya CV haikuweza kusomwa.");
    }
    event.target.value = "";
  }

  async function saveSettings() {
    setBusy("SETTINGS");
    setNotice("");
    setError("");
    try {
      const queries = queryText.split(/[\n,;]/).map(item => item.trim()).filter(Boolean);
      if (!queries.length) throw new Error("Weka angalau aina moja ya kazi ya remote kutafuta.");
      const result = await updateJobAutopilot({
        enabled: config.enabled === true,
        queries,
        interval_hours: Number(config.interval_hours) || 6,
        max_new_jobs: Number(config.max_new_jobs) || 12,
      });
      setConfig(current => ({ ...current, ...(result.config || {}), queries }));
      setQueryText(queries.join("\n"));
      setNotice("Mipangilio ya utafutaji imehifadhiwa.");
    } catch (err) {
      setError(err.message || "Mipangilio haikuweza kuhifadhiwa.");
    } finally {
      setBusy("");
    }
  }

  async function toggleAutopilot() {
    if (busy) return;
    const enabled = !config.enabled;
    setBusy("SETTINGS");
    setError("");
    setNotice("");
    try {
      const result = await updateJobAutopilot({ enabled });
      setConfig(current => ({ ...current, ...(result.config || {}), enabled }));
      setNotice(enabled ? "Utafutaji wa ratiba umewashwa." : "Utafutaji wa ratiba umesimamishwa.");
    } catch (err) {
      setError(err.message || "Hali ya Autopilot haikuweza kubadilishwa.");
    } finally {
      setBusy("");
    }
  }

  async function runNow() {
    setBusy("RUN");
    setNotice("");
    setError("");
    try {
      const queries = queryText.split(/[\n,;]/).map(item => item.trim()).filter(Boolean);
      if (!queries.length) throw new Error("Weka angalau aina moja ya kazi ya kutafuta.");
      await updateJobAutopilot({
        enabled: config.enabled === true,
        queries,
        interval_hours: Number(config.interval_hours) || 6,
        max_new_jobs: Number(config.max_new_jobs) || 12,
      });
      const result = await runJobAutopilotNow();
      await reloadWorkspace();
      setNotice(
        "Utafutaji umemaliza: nafasi mpya zinazokubali Tanzania " + Number(result.new_jobs || 0) +
        ", drafts " + Number(result.drafts_ready || 0) +
        ", zinasubiri CV " + Number(result.waiting_for_profile || 0) +
        ", hazikubali Tanzania " + Number(result.excluded_location || 0) +
        ", nchi haijathibitishwa " + Number(result.unverified_location || 0) +
        ". Maombi yaliyotumwa kiotomatiki: " + Number(result.applications_submitted || 0) + "."
      );
      setStatus(result.status === "SOURCE_ERROR"
        ? "BAADHI YA VYANZO HAVIKUJIBU"
        : result.status === "NO_ELIGIBLE_JOBS"
          ? "HAKUNA NAFASI ILIYOTHIBITISHWA KWA TANZANIA"
          : "UTAFUTAJI UMEKAMILIKA");
    } catch (err) {
      setError(err.message || "Job Autopilot imeshindwa kuendesha utafutaji.");
      setStatus("UTAFUTAJI UMESHINDWA");
    } finally {
      setBusy("");
    }
  }

  async function search(event) {
    event.preventDefault();
    const term = query.trim();
    if (term.length < 2) {
      setError("Andika aina ya kazi au ujuzi, angalau herufi mbili.");
      return;
    }
    setBusy("SEARCH");
    setError("");
    setWarning("");
    setNotice("");
    setStatus("INATAFUTA KWENYE REMOTEOK NA REMOTIVE...");
    try {
      const data = await researchJobs(term, 30);
      setResults(Array.isArray(data.results) ? data.results : []);
      setWarning(data.source_warnings?.length
        ? "Baadhi ya vyanzo havikupatikana. Matokeo yaliyopo bado yanaonyeshwa."
        : "");
      setStatus(data.count
        ? Number(data.count) + " NAFASI · " + (data.sources || []).join(" + ")
        : "HAKUNA NAFASI ZILIZOLINGANA");
    } catch (err) {
      setResults([]);
      setStatus("UTAFUTAJI UMESHINDWA");
      setError(err.message || "Vyanzo vya kazi havipatikani kwa sasa.");
    } finally {
      setBusy("");
    }
  }

  async function saveSearchResult(job) {
    const current = saved[job.url];
    if (current?.state === "SAVING" || current?.taskId) return;
    setSaved(rows => ({ ...rows, [job.url]: { ...rows[job.url], state: "SAVING" } }));
    setError("");
    try {
      const result = await saveJob(job);
      const taskId = result?.task?.id;
      setSaved(rows => ({
        ...rows,
        [job.url]: {
          ...rows[job.url],
          state: "SAVED",
          taskId,
          selectedStatus: rows[job.url]?.selectedStatus || "SAVED",
          evidenceUrl: rows[job.url]?.evidenceUrl || "",
          tracking: rows[job.url]?.tracking || {},
        },
      }));
      setStatus("IMEHIFADHIWA KWENYE TASKS · #" + taskId);
    } catch (err) {
      setSaved(rows => ({ ...rows, [job.url]: { ...rows[job.url], state: "FAILED" } }));
      setError(err.message || "Nafasi haikuweza kuhifadhiwa.");
    }
  }

  function changeSearchTracking(jobUrl, field, value) {
    setSaved(rows => ({
      ...rows,
      [jobUrl]: { ...rows[jobUrl], [field]: value },
    }));
  }

  async function updateSearchTracking(job) {
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
    setSaved(rows => ({ ...rows, [job.url]: { ...rows[job.url], state: "TRACKING" } }));
    try {
      const result = await updateJobTracking(record.taskId, {
        status: nextStatus,
        evidence_url: evidenceUrl,
        owner_confirmed: nextStatus !== "SAVED",
      });
      setSaved(rows => ({
        ...rows,
        [job.url]: {
          ...rows[job.url],
          state: "SAVED",
          taskId: record.taskId,
          selectedStatus: result.tracking.status,
          evidenceUrl: result.tracking.evidence_url || "",
          tracking: result.tracking,
        },
      }));
      setStatus("TRACKING SAVED · #" + record.taskId + " · " + nextStatus);
    } catch (err) {
      setSaved(rows => ({ ...rows, [job.url]: { ...rows[job.url], state: "SAVED" } }));
      setError(err.message || "Hali ya maombi haikuweza kuhifadhiwa.");
    }
  }

  function changeApplicationTracking(taskId, field, value) {
    setApplicationTracking(rows => ({
      ...rows,
      [taskId]: { ...(rows[taskId] || {}), [field]: value },
    }));
  }

  async function updateApplicationTracking(task) {
    const record = applicationTracking[task.id] || {};
    const nextStatus = record.status || "SAVED";
    const evidenceUrl = String(record.evidence_url || "").trim();
    if (evidenceUrl) {
      try {
        if (new URL(evidenceUrl).protocol !== "https:") throw new Error("HTTPS required");
      } catch {
        setError("Link ya ushahidi lazima ianze na https://");
        return;
      }
    }
    setBusy("TRACK-" + task.id);
    setError("");
    setNotice("");
    try {
      await updateJobTracking(task.id, {
        status: nextStatus,
        evidence_url: evidenceUrl,
        owner_confirmed: nextStatus !== "SAVED",
      });
      await reloadWorkspace();
      setStatus("TRACKING SAVED · #" + task.id + " · " + nextStatus);
      setNotice("Hali imehifadhiwa kama taarifa yako. MR AI hajathibitisha nje kuwa ombi limetumwa.");
    } catch (err) {
      setError(err.message || "Hali ya ombi haikuweza kuhifadhiwa.");
    } finally {
      setBusy("");
    }
  }

  async function copyText(value, label) {
    const textValue = String(value || "").trim();
    if (!textValue) {
      setError("Hakuna maandishi ya kunakili.");
      return;
    }
    try {
      if (!navigator?.clipboard?.writeText) throw new Error("Clipboard haipatikani kwenye browser hii.");
      await navigator.clipboard.writeText(textValue);
      setNotice(label + " imenakiliwa. Bandika kwenye fomu ya mwajiri.");
      setError("");
    } catch (err) {
      setError(err.message || "Maandishi hayakuweza kunakiliwa.");
    }
  }

  return (
    <div className="job-workspace">
      <header className="job-workspace-header">
        <div>
          <span className="eyebrow">MOG343 OPERATIONS · JOBS DESK</span>
          <h2>KAZI, CV NA MAOMBI</h2>
          <p>MR AI atafute fursa, atengeneze draft kwa CV yako na afuatilie hatua kwa hatua.</p>
        </div>
        <div className="job-profile-state" data-ready={profileReady ? "true" : "false"}>
          <span className="job-state-dot" />
          <div>
            <strong>{profileReady ? "CV IPO TAYARI" : "KAMILISHA CV YAKO"}</strong>
            <small>{profileReady ? "Inaweza kutumika kutengeneza drafts" : "Jina, email na skills au uzoefu vinahitajika"}</small>
          </div>
        </div>
      </header>

      <section className="job-metrics" aria-label="Job Autopilot summary">
        <JobMetric label="NAFASI ZILIZOPATIKANA" value={metrics.jobs_found} />
        <JobMetric label="DRAFTS TAYARI" value={metrics.drafts_ready} />
        <JobMetric label="ZINASUBIRI CV" value={metrics.waiting_for_profile} />
        <JobMetric label="AUTO-SUBMITTED" value={metrics.applications_submitted_automatically} tone="job-metric-muted" />
      </section>

      <section className="job-section job-profile-section">
        <div className="job-section-heading">
          <div>
            <span className="eyebrow">01 · CANDIDATE PROFILE</span>
            <h3>CV YAKO NA TAARIFA ZA MAOMBI</h3>
            <p>Hifadhi mara moja. MR AI atatumia taarifa hizi ku-match kazi na kuandaa barua za maombi.</p>
          </div>
          <span className="job-section-index">CV / 01</span>
        </div>

        <div className="job-profile-grid">
          <label>
            <span>JINA KAMILI</span>
            <input value={profile.full_name || ""} onChange={event => updateProfile("full_name", event.target.value)} autoComplete="name" placeholder="Majina yako kama yalivyo kwenye CV" />
          </label>
          <label>
            <span>EMAIL</span>
            <input type="email" value={profile.email || ""} onChange={event => updateProfile("email", event.target.value)} autoComplete="email" placeholder="jina@email.com" />
          </label>
          <label>
            <span>SIMU</span>
            <input value={profile.phone || ""} onChange={event => updateProfile("phone", event.target.value)} autoComplete="tel" placeholder="+255..." />
          </label>
          <label>
            <span>MAHALI</span>
            <input value={profile.location || ""} onChange={event => updateProfile("location", event.target.value)} placeholder="Dar es Salaam, Tanzania" />
          </label>
          <label className="job-profile-wide">
            <span>UJUZI / SKILLS · TENGANISHA KWA KOMA</span>
            <input value={skillsText} onChange={event => setSkillsText(event.target.value)} placeholder="Web development, graphic design, printing, cleaning..." />
          </label>
          <label className="job-profile-wide">
            <span>MUHTASARI WA UZOEFU</span>
            <textarea rows={3} value={profile.experience_summary || ""} onChange={event => updateProfile("experience_summary", event.target.value)} placeholder="Andika uzoefu wako halisi, miradi, mafunzo na kazi ulizowahi kufanya." />
          </label>
          <label className="job-profile-wide">
            <span>PORTFOLIO / LINK YA KAZI · HIARI</span>
            <input type="url" value={profile.portfolio_url || ""} onChange={event => updateProfile("portfolio_url", event.target.value)} placeholder="https://..." />
          </label>
        </div>

        <div className="job-cv-editor">
          <div className="job-cv-editor-head">
            <div>
              <strong>MAANDISHI YA CV</strong>
              <small>Yatumike kwa kulinganisha ujuzi na kuandika maombi bila kubuni uzoefu.</small>
            </div>
            <span>{String(profile.resume_text || "").length}/6000</span>
          </div>
          <textarea
            className="job-cv-textarea"
            rows={8}
            maxLength={6000}
            value={profile.resume_text || ""}
            onChange={event => updateProfile("resume_text", event.target.value)}
            placeholder={"Bandika CV yako yote hapa.\n\nMR AI atatumia Professional Summary, Technical Skills na taarifa nyingine ulizoandika."}
          />
          <div className="job-cv-tools">
            <label className="job-file-pick">
              PAKIA CV (.TXT / .MD)
              <input type="file" accept=".txt,.md,.text,text/plain,text/markdown" onChange={importTextFile} />
            </label>
            <button className="mini-button" type="button" disabled={Boolean(busy) || loading} onClick={importProfileFromMemory}>
              {busy === "IMPORT" ? "INAHAMISHA..." : "LETA CV KUTOKA MEMORY"}
            </button>
          </div>
        </div>

        <div className="job-profile-footer">
          <p>CV ni yako na imehifadhiwa ndani ya akaunti yako. Taarifa zisizo kwenye CV hazitaongezwa kwa kubahatisha.</p>
          <button className="primary-button" type="button" disabled={Boolean(busy) || loading} onClick={saveProfile}>
            {busy === "PROFILE" ? "INAHIFADHI..." : "HIFADHI CV & PROFILE"}
          </button>
        </div>
      </section>

      <section className="job-section">
        <div className="job-section-heading">
          <div>
            <span className="eyebrow">02 · LOCAL OPPORTUNITIES</span>
            <h3>KAZI NDOGO NA VIBARUA TANZANIA</h3>
            <p>Portal za nje zilizo wazi. Fungua tangazo, hakiki mwajiri na masharti kabla ya kukubali kazi.</p>
          </div>
          <span className="job-section-index">TANZANIA / 02</span>
        </div>
        <div className="job-local-grid">
          {LOCAL_JOB_SOURCES.map(source => (
            <article className="job-local-card" key={source.title}>
              <span>{source.type}</span>
              <h4>{source.title}</h4>
              <p>{source.description}</p>
              <a href={source.url} target="_blank" rel="noreferrer">{source.action} ↗</a>
            </article>
          ))}
        </div>
        <p className="job-safety-note">USALAMA: Usilipe deposit au ada ya kupewa kazi. Hakiki kampuni, mahali pa kazi, malipo na mawasiliano kabla ya kutoa taarifa nyeti.</p>
      </section>

      <section className="job-section job-autopilot-section">
        <div className="job-section-heading">
          <div>
            <span className="eyebrow">03 · AUTOMATED REMOTE SEARCH</span>
            <h3>MR AI JOB AUTOPILOT</h3>
            <p>Hutafuta remote/online kupitia public feeds. Draft huandaliwa tu pale tangazo linaposema Tanzania au worldwide; "Remote" peke yake haitoshi.</p>
          </div>
          <span className={"job-autopilot-pill" + (config.enabled ? " is-on" : "")}>
            {config.enabled ? "RATIBA IMEWASHWA" : "RATIBA IMEZIMWA"}
          </span>
        </div>
        <div className="job-autopilot-controls">
          <label className="job-query-field">
            <span>AINA ZA KAZI ZA KUTAFUTA · MOJA KWA KILA MSTARI</span>
            <textarea rows={4} value={queryText} onChange={event => setQueryText(event.target.value)} placeholder={"graphic designer\nvirtual assistant\ntranscription"} />
          </label>
          <label>
            <span>MARUDIO</span>
            <select value={config.interval_hours || 6} onChange={event => setConfig(current => ({ ...current, interval_hours: Number(event.target.value) }))}>
              {[1, 3, 6, 12, 24].map(hours => <option value={hours} key={hours}>Kila saa {hours}</option>)}
            </select>
          </label>
          <label>
            <span>NAFASI MPYA KWA RUN</span>
            <select value={config.max_new_jobs || 12} onChange={event => setConfig(current => ({ ...current, max_new_jobs: Number(event.target.value) }))}>
              {[5, 10, 12, 20, 30].map(count => <option value={count} key={count}>{count}</option>)}
            </select>
          </label>
        </div>
        <div className="job-quick-searches">
          <span>TAFUTA HARAKA:</span>
          {QUICK_SEARCHES.map(term => (
            <button type="button" key={term} onClick={() => setQueryText(current => {
              const currentTerms = current.split(/[\n,;]/).map(item => item.trim()).filter(Boolean);
              return currentTerms.includes(term) ? current : currentTerms.concat(term).join("\n");
            })}>{term}</button>
          ))}
        </div>
        <div className="job-action-row">
          <button className="mini-button" type="button" disabled={Boolean(busy) || loading} onClick={toggleAutopilot}>
            {busy === "SETTINGS" ? "INAHIFADHI..." : config.enabled ? "ZIMA RATIBA" : "WASHA RATIBA"}
          </button>
          <button className="mini-button" type="button" disabled={Boolean(busy) || loading} onClick={saveSettings}>
            HIFADHI MIPANGILIO
          </button>
          <button className="primary-button" type="button" disabled={Boolean(busy) || loading} onClick={runNow}>
            {busy === "RUN" ? "INATAFUTA..." : "TAFUTA KAZI SASA"}
          </button>
        </div>
        <p className="job-autopilot-truth">
          Kwa sasa Autopilot hutafuta na kuandaa barua. Haitumi maombi yenyewe kwenye tovuti za waajiri; idadi ya maombi yaliyotumwa kiotomatiki inabaki 0 mpaka njia ya kutuma ithibitishwe.
        </p>
      </section>

      <section className="job-section">
        <div className="job-section-heading">
          <div>
            <span className="eyebrow">04 · LIVE REMOTE LISTINGS</span>
            <h3>TAFUTA KAZI ZA ONLINE</h3>
            <p>Utafutaji wa papo hapo kwenye RemoteOK na Remotive.</p>
          </div>
          <span className="job-section-index">{results.length} MATOKEO</span>
        </div>
        <form className="job-search-form" onSubmit={search}>
          <input
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Mfano: Python developer, React, customer support"
            aria-label="Job search terms"
            minLength={2}
            required
          />
          <button className="primary-button" disabled={Boolean(busy)}>{busy === "SEARCH" ? "INATAFUTA..." : "SEARCH JOBS"}</button>
        </form>
        <div className="tool-status" role="status" aria-live="polite">{status}</div>
        {error && <p className="auth-error" role="alert">{error}</p>}
        {warning && <p className="job-inline-warning" role="status">{warning}</p>}
        {notice && <p className="tool-status" role="status" aria-live="polite">{notice}</p>}
        <div className="job-quick-searches">
          <span>MAJARIBIO YA HARAKA:</span>
          {QUICK_SEARCHES.slice(0, 5).map(term => (
            <button type="button" key={term} onClick={() => setQuery(term)}>{term}</button>
          ))}
        </div>
        <div className="job-results">
          {results.map(job => {
            const record = saved[job.url];
            const tracking = record?.tracking || {};
            return (
              <article className="job-result-card" key={job.url}>
                <div className="job-result-copy">
                  <span className="job-result-source">{job.source || "PUBLIC JOB FEED"} · {dateLabel(job.published_at)}</span>
                  <h4>{job.title}</h4>
                  <p className="job-company">{job.company} · {job.location}</p>
                  {job.location_eligibility && (
                    <p className={job.location_eligibility === "ELIGIBLE" ? "job-eligibility-note is-eligible" : "job-eligibility-note"}>
                      <strong>{job.location_eligibility === "ELIGIBLE" ? "TANZANIA ELIGIBLE" : job.location_eligibility === "NOT_ELIGIBLE" ? "HAIKUBALI TANZANIA" : "LOCATION HAITHIBITISHWI"}</strong>
                      {" · "}{job.eligibility_reason}
                    </p>
                  )}
                  {job.description && <p className="job-result-description">{job.description}</p>}
                  {job.tags?.length > 0 && <div className="job-tags">{job.tags.map(tag => <span key={tag}>{tag}</span>)}</div>}
                </div>
                <div className="job-result-actions">
                  <a href={job.url} target="_blank" rel="noreferrer">ANGALIA TANGAZO ↗</a>
                  <button
                    className="mini-button"
                    type="button"
                    disabled={record?.state === "SAVING" || Boolean(record?.taskId)}
                    onClick={() => saveSearchResult(job)}
                  >
                    {record?.state === "SAVING" ? "INAHIFADHI..." : record?.taskId ? "SAVED · #" + record.taskId : record?.state === "FAILED" ? "JARIBU TENA" : "SAVE TO TASKS"}
                  </button>
                </div>
                {record?.taskId && (
                  <div className="job-search-tracking">
                    <label htmlFor={"job-status-" + record.taskId}>APPLICATION TRACKING · TASK #{record.taskId}</label>
                    <select
                      id={"job-status-" + record.taskId}
                      value={record.selectedStatus || "SAVED"}
                      onChange={event => changeSearchTracking(job.url, "selectedStatus", event.target.value)}
                      disabled={record.state === "TRACKING"}
                    >
                      {TRACKING_STATUSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                    <input
                      type="url"
                      value={record.evidenceUrl || ""}
                      onChange={event => changeSearchTracking(job.url, "evidenceUrl", event.target.value)}
                      placeholder="Optional: link ya ushahidi (HTTPS)"
                      aria-label="Optional evidence URL"
                      disabled={record.state === "TRACKING"}
                    />
                    <div className="job-track-actions">
                      <button className="mini-button" type="button" onClick={() => updateSearchTracking(job)} disabled={record.state === "TRACKING"}>
                        {record.state === "TRACKING" ? "INAHIFADHI..." : "SAVE STATUS"}
                      </button>
                      <span className="badge">{tracking.status || "SAVED"}</span>
                      {tracking.owner_confirmed && <small>OWNER CONFIRMED</small>}
                      {tracking.evidence_url && <small>EVIDENCE LINK NOT CHECKED</small>}
                    </div>
                    <small>Hali hii ni taarifa yako. Kiungo cha ushahidi hakijakaguliwa moja kwa moja.</small>
                  </div>
                )}
              </article>
            );
          })}
          {!busy && results.length === 0 && (
            <div className="job-empty">Andika ujuzi au aina ya kazi hapo juu. Nafasi zitakazoonekana zitakuwa na link ya tangazo lake la asili.</div>
          )}
        </div>
      </section>

      <section className="job-section job-application-section">
        <div className="job-section-heading">
          <div>
            <span className="eyebrow">05 · APPLICATION PIPELINE</span>
            <h3>MAOMBI YALIYOANDALIWA</h3>
            <p>Fungua tangazo, nakili barua, tuma kupitia mwajiri na kisha rekodi hatua yako.</p>
          </div>
          <span className="job-section-index">{applicationRows.length} MAOMBI</span>
        </div>

        {applicationRows.length > 0 ? (
          <div className="job-application-list">
            {applicationRows.map(({ task, packet, job, draft }) => {
              const record = applicationTracking[task.id] || {};
              const tracking = packet.tracking || {};
              const taskStatus = String(task.status || packet.status || "").toUpperCase();
              return (
                <article className="job-application-card" key={task.id}>
                  <div className="job-application-top">
                    <div>
                      <span className="job-result-source">TASK #{task.id} · {job.source || "JOB AUTOPILOT"}</span>
                      <h4>{job.title || task.title}</h4>
                      <p>{job.company || "Mwajiri hajaorodheshwa"} · {job.location || "Remote"}</p>
                    </div>
                    <span className={"job-application-status state-" + taskStatus.toLowerCase().replaceAll("_", "-")}>
                      {statusLabel(tracking.status || taskStatus)}
                    </span>
                  </div>

                  {packet.location_eligibility && packet.location_eligibility !== "ELIGIBLE" && (
                    <p className="job-eligibility-note">
                      <strong>{packet.location_eligibility === "NOT_ELIGIBLE" ? "HAIKUBALI TANZANIA" : "LOCATION HAITHIBITISHWI"}</strong>
                      {" · "}{packet.eligibility_reason || task.error}
                    </p>
                  )}

                  {Number.isFinite(Number(packet.match_score)) && packet.match_score !== null && (
                    <div className="job-match-score">
                      <span>CV MATCH</span>
                      <strong>{Math.max(0, Math.min(100, Number(packet.match_score)))}%</strong>
                    </div>
                  )}

                  {draft ? (
                    <div className="job-draft-box">
                      <div className="job-draft-heading">
                        <strong>BARUA YA MAOMBI · DRAFT</strong>
                        <small>IMETENGENEZWA KUTOKA KWENYE CV YAKO</small>
                      </div>
                      <p className="job-draft-subject"><strong>Subject:</strong> {draft.subject || "Application for " + (job.title || "the role")}</p>
                      <pre>{draft.cover_letter || "Draft haijapatikana."}</pre>
                      <div className="job-action-row">
                        <button className="mini-button" type="button" onClick={() => copyText(draft.subject || "", "Subject")}>NAKILI SUBJECT</button>
                        <button className="primary-button" type="button" onClick={() => copyText(draft.cover_letter || "", "Barua ya maombi")}>NAKILI BARUA</button>
                      </div>
                    </div>
                  ) : (
                    <div className="job-waiting-note">
                      {taskStatus === "WAITING_FOR_PROFILE"
                        ? "CV/profile haijakamilika. Hifadhi jina, email na skills au uzoefu ili MR AI atengeneze draft."
                        : task.error || packet.eligibility_reason || packet.submission?.reason || "Draft haipo bado."}
                    </div>
                  )}

                  <div className="job-application-actions">
                    {job.url && <a href={job.url} target="_blank" rel="noreferrer">FUNGUA TANGAZO / OMBA KWA MWAJIRI ↗</a>}
                  </div>

                  <div className="job-application-tracking">
                    <label htmlFor={"application-status-" + task.id}>HATUA YAKO YA MAOMBI</label>
                    <select
                      id={"application-status-" + task.id}
                      value={record.status || tracking.status || "SAVED"}
                      onChange={event => changeApplicationTracking(task.id, "status", event.target.value)}
                      disabled={busy === "TRACK-" + task.id}
                    >
                      {TRACKING_STATUSES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                    </select>
                    <input
                      type="url"
                      value={record.evidence_url ?? tracking.evidence_url ?? ""}
                      onChange={event => changeApplicationTracking(task.id, "evidence_url", event.target.value)}
                      placeholder="Link ya confirmation/email (HTTPS) · hiari"
                      aria-label="Application evidence URL"
                      disabled={busy === "TRACK-" + task.id}
                    />
                    <div className="job-action-row">
                      <button className="mini-button" type="button" disabled={Boolean(busy)} onClick={() => updateApplicationTracking(task)}>
                        {busy === "TRACK-" + task.id ? "INAHIFADHI..." : "HIFADHI HATUA"}
                      </button>
                      {tracking.owner_confirmed && <small>OWNER CONFIRMED</small>}
                      {tracking.evidence_url && <small>EVIDENCE LINK NOT CHECKED</small>}
                    </div>
                    <small>Hali ni taarifa uliyoweka mwenyewe. MR AI hawezi kuiita imethibitishwa bila ushahidi huru.</small>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="job-empty">
            Bado hakuna application draft. Hifadhi CV yako kisha bonyeza TAFUTA KAZI SASA.
          </div>
        )}
      </section>
    </div>
  );
}
