import { useEffect, useMemo, useState } from "react";
import {
  applyCodingAgentPlan,
  checkCodingAgentCommit,
  getCodingAgentStatus,
  getTools,
  planCodingAgentTask,
  searchToolWeb,
} from "../api";

function statusClass(status) {
  return String(status).toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

export default function ToolBox() {
  const [registry, setRegistry] = useState(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searchStatus, setSearchStatus] = useState("READY");
  const [codingStatus, setCodingStatus] = useState(null);
  const [codingRequest, setCodingRequest] = useState("");
  const [codingBusy, setCodingBusy] = useState("");
  const [codingError, setCodingError] = useState("");
  const [codingPlan, setCodingPlan] = useState(null);
  const [codingExecution, setCodingExecution] = useState(null);

  useEffect(() => {
    getTools().then(setRegistry).catch(() => setRegistry({ tools: [] }));
    getCodingAgentStatus().then(setCodingStatus).catch(error => setCodingStatus({
      status: "ERROR",
      configured: false,
      can_plan: false,
      can_apply: false,
      message: error?.message || "Coding Agent status could not be loaded.",
    }));
  }, []);

  useEffect(() => {
    const commitSha = codingExecution?.commit_sha;
    const taskId = codingExecution?.task_id;
    const terminal = ["PASSED", "FAILED"].includes(String(codingExecution?.ci || "").toUpperCase());
    if (!commitSha || !taskId || terminal) return undefined;

    let cancelled = false;
    async function pollChecks() {
      try {
        const result = await checkCodingAgentCommit(commitSha, taskId);
        if (cancelled) return;
        setCodingExecution(current => current ? {
          ...current,
          ci: result.status,
          checks: result.checks || [],
          task: result.task || current.task,
        } : current);
      } catch {
        // Network hiccups do not mark the job as passed or failed; the next poll retries.
      }
    }
    pollChecks();
    const timer = window.setInterval(pollChecks, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [codingExecution?.commit_sha, codingExecution?.task_id, ["PASSED", "FAILED"].includes(String(codingExecution?.ci || "").toUpperCase())]);

  async function prepareCodingPatch() {
    if (!codingRequest.trim() || codingBusy) return;
    setCodingBusy("PLAN");
    setCodingError("");
    setCodingExecution(null);
    setCodingPlan(null);
    try {
      const result = await planCodingAgentTask(codingRequest.trim());
      if (result?.status !== "PLAN_READY" || !result.plan || !result.proposal_signature) {
        throw new Error(result?.message || "Coding Agent did not return a signed patch proposal.");
      }
      setCodingPlan(result);
    } catch (error) {
      setCodingError(error?.message || "Coding Agent failed to prepare a patch.");
    } finally {
      setCodingBusy("");
    }
  }

  async function applyCodingPatch() {
    if (!codingPlan || codingBusy) return;
    setCodingBusy("APPLY");
    setCodingError("");
    try {
      const result = await applyCodingAgentPlan(codingPlan.plan, codingPlan.proposal_signature);
      setCodingExecution({ ...result, ci: result.ci || "RUNNING" });
      setCodingPlan(null);
    } catch (error) {
      setCodingError(error?.message || "Coding Agent could not apply the patch.");
    } finally {
      setCodingBusy("");
    }
  }

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

      <section className="coding-agent-console" aria-labelledby="coding-agent-title">
        <div className="coding-agent-console-head">
          <div>
            <span className="eyebrow">AUTONOMOUS ENGINEERING // CODEX-STYLE WORKFLOW</span>
            <h3 id="coding-agent-title">MR AI Coding Agent</h3>
          </div>
          <span className={`coding-agent-state ${statusClass(codingStatus?.status || "CONNECTING")}`}>
            {codingStatus?.status || "CHECKING"}
          </span>
        </div>
        <p className="coding-agent-description">
          Inspects your GitHub code, proposes focused edits and regression tests, creates an isolated branch and opens a pull request. GitHub Actions verifies the patch; production is never edited directly.
        </p>
        <div className="coding-agent-capabilities">
          <span>REPO REVIEW</span><span>PATCH + TESTS</span><span>BRANCH + PR</span><span>CI EVIDENCE</span>
        </div>
        {codingStatus?.repository && (
          <div className="coding-agent-connection">
            <strong>{codingStatus.repository}</strong>
            <span>Base: {codingStatus.base_branch || "main"} · AI: {codingStatus.ai_provider || "FREE PROVIDER NOT READY"}</span>
          </div>
        )}
        {!codingStatus?.can_plan && (
          <div className="coding-agent-not-ready" role="status">
            {codingStatus?.message || "Checking GitHub workspace and free AI provider."}
            <small>Render backend must have CODING_GITHUB_TOKEN, CODING_GITHUB_REPOSITORY=mipox2922-art/MR-AI-STAN, and a free OpenRouter route or Gemini FREE tier. Never paste tokens into this form.</small>
          </div>
        )}
        <label className="coding-agent-label" htmlFor="coding-agent-request">CODING MISSION</label>
        <textarea
          id="coding-agent-request"
          value={codingRequest}
          onChange={event => setCodingRequest(event.target.value)}
          rows={3}
          maxLength={6000}
          placeholder="Mfano: Tafuta kwa nini chat inarudia salamu tu, rekebisha chanzo, ongeza regression tests na uandae PR."
          disabled={Boolean(codingBusy)}
        />
        <div className="coding-agent-actions">
          <button type="button" className="primary-button" onClick={prepareCodingPatch} disabled={!codingStatus?.can_plan || !codingRequest.trim() || Boolean(codingBusy)}>
            {codingBusy === "PLAN" ? "INSPECTING + PLANNING..." : "ANALYZE REPO & PREPARE PATCH"}
          </button>
          {codingPlan && (
            <button type="button" className="primary-button" onClick={applyCodingPatch} disabled={!codingStatus?.can_apply || Boolean(codingBusy)}>
              {codingBusy === "APPLY" ? "COMMITTING + OPENING PR..." : "APPLY REVIEWED PATCH + OPEN PR"}
            </button>
          )}
        </div>
        {codingError && <div className="coding-agent-error" role="alert">{codingError}</div>}
        {codingPlan?.plan && (
          <div className="coding-agent-plan">
            <div className="coding-agent-plan-head">
              <strong>PATCH READY FOR OWNER REVIEW</strong>
              <span>RISK: {codingPlan.plan.risk}</span>
            </div>
            <p>{codingPlan.plan.summary}</p>
            <small>Files read: {codingPlan.plan.files_reviewed?.length || 0} · Files changed: {codingPlan.plan.changes?.length || 0} · Provider: {codingPlan.plan.provider}</small>
            <div className="coding-agent-file-list">
              {(codingPlan.plan.changes || []).map(change => (
                <details key={change.path} className="coding-agent-file">
                  <summary>{change.path} · {change.action}</summary>
                  <pre>{change.diff || "No textual diff returned."}</pre>
                </details>
              ))}
            </div>
            {codingPlan.plan.tests_to_run?.length > 0 && (
              <div className="coding-agent-test-plan">
                <strong>CI / TEST PLAN</strong>
                <ul>{codingPlan.plan.tests_to_run.map((test, index) => <li key={index}>{test}</li>)}</ul>
              </div>
            )}
            <p className="coding-agent-safety">No source has been changed yet. Applying creates a branch and pull request; you can review the diff before merging.</p>
          </div>
        )}
        {codingExecution && (
          <div className="coding-agent-execution" role="status" aria-live="polite">
            <div className="coding-agent-plan-head">
              <strong>CODING TASK #{codingExecution.task_id || "—"}</strong>
              <span>CI: {codingExecution.ci || "PENDING"}</span>
            </div>
            <p>{codingExecution.message || codingExecution.summary || "The patch was submitted to GitHub."}</p>
            <div className="coding-agent-links">
              {codingExecution.pull_request?.url && <a href={codingExecution.pull_request.url} target="_blank" rel="noreferrer">OPEN PULL REQUEST #{codingExecution.pull_request.number}</a>}
              {codingExecution.commit_url && <a href={codingExecution.commit_url} target="_blank" rel="noreferrer">VIEW COMMIT</a>}
              {codingExecution.task?.status && <span>Task status: {codingExecution.task.status}</span>}
            </div>
            {codingExecution.checks?.length > 0 && (
              <div className="coding-agent-check-list">
                {codingExecution.checks.map((check, index) => (
                  <div key={check.name || index}>
                    <span>{check.name || "GitHub check"}</span>
                    <strong>{check.conclusion || check.status || "PENDING"}</strong>
                    {check.details_url && <a href={check.details_url} target="_blank" rel="noreferrer">logs</a>}
                  </div>
                ))}
              </div>
            )}
            <small>Tests are only marked passed after GitHub Actions confirms success. MR AI does not auto-merge.</small>
          </div>
        )}
      </section>

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
