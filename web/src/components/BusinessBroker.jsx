import { useCallback, useEffect, useState } from "react";
import {
  getBrokerStatus,
  getBrokerOpportunities,
  researchBrokerOpportunities,
  prepareBrokerOutreach,
  updateBrokerOpportunity,
} from "../api";

const OPPORTUNITY_TYPES = [
  ["REMOTE_WORK", "Remote work and freelance"],
  ["CLIENT_LEAD", "Potential customers / clients"],
  ["SUPPLIER", "Suppliers and manufacturers"],
  ["PRODUCT", "Products and sourcing"],
  ["AFFILIATE", "Affiliate / referral programs"],
  ["GENERAL", "Other business opportunities"],
];

const STATUS_OPTIONS = [
  ["UNVERIFIED", "Unverified"],
  ["RESEARCHED", "Researched"],
  ["SHORTLISTED", "Shortlisted"],
  ["CONTACT_DRAFTED", "Draft prepared"],
  ["CONTACTED", "Contacted"],
  ["FOLLOW_UP_DUE", "Follow-up due"],
  ["WON", "Won"],
  ["LOST", "Lost"],
];

const MONEY_FIELDS = [
  ["selling_price", "Selling price"],
  ["supplier_cost", "Supplier / production cost"],
  ["shipping_cost", "Shipping / fulfilment"],
  ["fees_taxes", "Known fees / taxes"],
  ["commission", "Commission income"],
  ["required_capital", "Capital required"],
  ["actual_revenue", "Actual revenue / deal income"],
  ["actual_cost", "Actual completed-deal cost"],
];

function formatDate(value) {
  if (!value) return "Not recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "Not recorded"
    : parsed.toLocaleString("en-GB", { timeZone: "Africa/Dar_es_Salaam" });
}

function money(value, currency) {
  if (value === null || value === undefined || value === "") return "Unknown";
  const formatted = Number(value).toLocaleString("en-GB", { maximumFractionDigits: 2 });
  return currency ? currency + " " + formatted : formatted;
}

function BrokerOpportunityCard({ opportunity, onUpdate, onPrepare }) {
  const [status, setStatus] = useState(opportunity.status || "RESEARCHED");
  const [currency, setCurrency] = useState(opportunity.currency || "");
  const [amounts, setAmounts] = useState(() => Object.fromEntries(
    MONEY_FIELDS.map(([key]) => [key, opportunity[key] ?? ""])
  ));
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    setStatus(opportunity.status || "RESEARCHED");
    setCurrency(opportunity.currency || "");
    setAmounts(Object.fromEntries(MONEY_FIELDS.map(([key]) => [key, opportunity[key] ?? ""])));
  }, [opportunity]);

  async function saveTracking() {
    setBusy("SAVE");
    setError("");
    setNotice("");
    try {
      const payload = { status, currency: currency.trim() || null };
      for (const [key] of MONEY_FIELDS) {
        const raw = amounts[key];
        payload[key] = raw === "" || raw === null ? null : Number(raw);
        if (payload[key] !== null && (!Number.isFinite(payload[key]) || payload[key] < 0)) {
          throw new Error(key.replaceAll("_", " ") + " must be a non-negative number.");
        }
      }
      const updated = await updateBrokerOpportunity(opportunity.id, payload);
      setNotice("Opportunity record saved.");
      onUpdate(updated);
    } catch (err) {
      setError(err.message || "Could not save this opportunity.");
    } finally {
      setBusy("");
    }
  }

  async function prepareDraft() {
    setBusy("DRAFT");
    setError("");
    setNotice("");
    try {
      const result = await onPrepare(opportunity.id);
      if (result && result.opportunity) onUpdate(result.opportunity);
      setNotice("Draft stored. Nothing was sent.");
    } catch (err) {
      setError(err.message || "Could not prepare the outreach draft.");
    } finally {
      setBusy("");
    }
  }

  const evidence = opportunity.evidence && typeof opportunity.evidence === "object" ? opportunity.evidence : {};
  const matchedSourceDate = formatDate(opportunity.source_checked_at);

  return (
    <article className="agent-card" style={{ alignItems: "start", display: "grid", gridTemplateColumns: "auto minmax(0,1fr)", gap: 14 }}>
      <div className="agent-icon">⇄</div>
      <div style={{ minWidth: 0, width: "100%" }}>
        <div style={{ display: "flex", alignItems: "start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <strong>{opportunity.title}</strong>
            <span>{opportunity.organization || opportunity.opportunity_type.replaceAll("_", " ")}</span>
            <small>{opportunity.source_name} · Source checked: {matchedSourceDate}</small>
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <span className="badge">FIT {opportunity.fit_score}/100</span>
            <span className="badge">RISK {opportunity.risk_level}</span>
          </div>
        </div>

        {opportunity.summary && <p style={{ margin: "10px 0", overflowWrap: "anywhere" }}>{opportunity.summary}</p>}
        <p style={{ margin: "6px 0", opacity: 0.85, fontSize: 12 }}>{opportunity.fit_rationale}</p>
        <p style={{ margin: "6px 0", opacity: 0.8, fontSize: 12 }}>
          Source response received. Identity verified: {evidence.identity_verified ? "YES" : "NO"}.
          {" "}Price verified: {evidence.pricing_verified ? "YES" : "NO"}.
        </p>
        <a href={opportunity.source_url} target="_blank" rel="noreferrer">OPEN ORIGINAL SOURCE ↗</a>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(155px, 1fr))", gap: 10, marginTop: 14 }}>
          <div className="panel" style={{ padding: 10 }}>
            <small>GROSS MARGIN</small>
            <strong style={{ display: "block", marginTop: 5 }}>
              {money(opportunity.gross_margin_amount, currency)}{opportunity.gross_margin_percent !== null ? " · " + opportunity.gross_margin_percent + "%" : ""}
            </strong>
          </div>
          <div className="panel" style={{ padding: 10 }}>
            <small>NET MARGIN</small>
            <strong style={{ display: "block", marginTop: 5 }}>{money(opportunity.net_margin_amount, currency)}</strong>
          </div>
          <div className="panel" style={{ padding: 10 }}>
            <small>CAPITAL REQUIRED</small>
            <strong style={{ display: "block", marginTop: 5 }}>{money(opportunity.required_capital, currency)}</strong>
          </div>
        </div>

        <details style={{ marginTop: 14 }}>
          <summary style={{ cursor: "pointer" }}>Update pricing, status and outcome</summary>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 10, marginTop: 12 }}>
            <label>
              Pipeline status
              <select value={status} onChange={event => setStatus(event.target.value)}>
                {STATUS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>
              Currency code
              <input value={currency} onChange={event => setCurrency(event.target.value.toUpperCase())} maxLength={12} placeholder="e.g. USD, TZS" />
            </label>
            {MONEY_FIELDS.map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={amounts[key]}
                  onChange={event => setAmounts(previous => ({ ...previous, [key]: event.target.value }))}
                  placeholder="Unknown"
                />
              </label>
            ))}
          </div>
          <button type="button" className="mini-button" style={{ marginTop: 12 }} disabled={Boolean(busy)} onClick={saveTracking}>
            {busy === "SAVE" ? "SAVING..." : "SAVE PIPELINE DATA"}
          </button>
        </details>

        {opportunity.outreach_body && (
          <details style={{ marginTop: 12 }}>
            <summary style={{ cursor: "pointer" }}>Outreach draft · not sent</summary>
            <strong style={{ display: "block", marginTop: 10 }}>{opportunity.outreach_subject}</strong>
            <textarea readOnly value={opportunity.outreach_body} rows={6} style={{ width: "100%", marginTop: 8, resize: "vertical" }} />
            <small>Follow-up task: {opportunity.follow_up_task_id ? "#" + opportunity.follow_up_task_id : "not created"} · Due: {formatDate(opportunity.follow_up_at)}</small>
          </details>
        )}
        {!opportunity.outreach_body && (
          <button type="button" className="mini-button" style={{ marginTop: 12 }} disabled={Boolean(busy)} onClick={prepareDraft}>
            {busy === "DRAFT" ? "PREPARING..." : "PREPARE DRAFT + FOLLOW-UP"}
          </button>
        )}
        {notice && <p className="tool-status" role="status">{notice}</p>}
        {error && <p className="auth-error" role="alert">{error}</p>}
      </div>
    </article>
  );
}

export default function BusinessBroker() {
  const [goal, setGoal] = useState("Find remote graphic design jobs");
  const [type, setType] = useState("REMOTE_WORK");
  const [offer, setOffer] = useState("graphic design and branding");
  const [status, setStatus] = useState(null);
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [sourceWarnings, setSourceWarnings] = useState([]);

  const refresh = useCallback(async () => {
    const [statusResult, rows] = await Promise.all([
      getBrokerStatus(),
      getBrokerOpportunities({ limit: 50 }),
    ]);
    setStatus(statusResult);
    setItems(Array.isArray(rows) ? rows : []);
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([getBrokerStatus(), getBrokerOpportunities({ limit: 50 })])
      .then(([statusResult, rows]) => {
        if (!active) return;
        setStatus(statusResult);
        setItems(Array.isArray(rows) ? rows : []);
      })
      .catch(err => { if (active) setError(err.message || "Broker API is unavailable."); });
    return () => { active = false; };
  }, []);

  async function search(event) {
    event.preventDefault();
    if (busy) return;
    setBusy("SEARCH");
    setError("");
    setNotice("");
    setSourceWarnings([]);
    try {
      const result = await researchBrokerOpportunities({
        goal: goal.trim(),
        opportunity_type: type,
        max_results: 15,
        prepare_workflow: true,
        offer: offer.trim() || null,
      });
      setSourceWarnings(result.source_warnings || []);
      if (Array.isArray(result.opportunities)) {
        setItems(previous => {
          const byId = new Map(previous.map(item => [item.id, item]));
          result.opportunities.forEach(item => byId.set(item.id, item));
          return [...byId.values()].sort((a, b) => (b.fit_score || 0) - (a.fit_score || 0));
        });
      }
      setNotice((result.status || "UNKNOWN") + " · " + (result.saved_count || 0) + " saved · " + (result.new_count || 0) + " new · " + (result.updated_count || 0) + " refreshed. " + (result.message || ""));
      if (result.status === "NOT_CONNECTED") {
        setNotice(result.message || "Selected research source is not connected.");
      }
    } catch (err) {
      setError(err.message || "Research failed.");
    } finally {
      setBusy("");
    }
  }

  async function prepare(opportunityId) {
    const result = await prepareBrokerOutreach(opportunityId, { offer: offer.trim() || null, follow_up_days: 3 });
    await refresh();
    return result;
  }

  function updateRow(updated) {
    setItems(previous => previous.map(item => item.id === updated.id ? updated : item));
  }

  return (
    <>
      <section className="panel large-panel">
        <div className="panel-head">
          <div>
            <span className="eyebrow">MOG343 · RESEARCH / MATCH / FOLLOW UP</span>
            <h2>Business Broker</h2>
            <p>Research public opportunities, keep source evidence, rank fit, estimate margins only from supplied costs, and prepare drafts. External contact, orders and payments are never automatic.</p>
          </div>
          <span className="badge">{items.length} PIPELINE</span>
        </div>

        <div className="tool-status" role="status" aria-live="polite">
          {status
            ? "PIPELINE AVAILABLE · SUPPLIER / CLIENT SEARCH: " + status.business_supplier_search + " · PUBLIC JOB FEEDS: " + status.public_job_feeds.join(", ")
            : "Checking broker connection..."}
        </div>

        <form className="planner-row" onSubmit={search} style={{ display: "grid", gap: 10 }}>
          <label>
            Mission goal
            <textarea value={goal} onChange={event => setGoal(event.target.value)} rows={2} minLength={3} maxLength={500} required placeholder="e.g. Find businesses that need graphic design" />
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10 }}>
            <label>
              Opportunity type
              <select value={type} onChange={event => setType(event.target.value)}>
                {OPPORTUNITY_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>
              Service offered / context
              <input value={offer} onChange={event => setOffer(event.target.value)} maxLength={800} placeholder="Use only skills or services you can actually provide" />
            </label>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <button className="primary-button" type="submit" disabled={Boolean(busy) || goal.trim().length < 3}>
              {busy === "SEARCH" ? "RESEARCHING SOURCES..." : "RESEARCH + SAVE PIPELINE"}
            </button>
            <button className="mini-button" type="button" disabled={Boolean(busy)} onClick={() => refresh().catch(err => setError(err.message))}>REFRESH SAVED</button>
          </div>
        </form>
        {notice && <p className="tool-status" role="status" aria-live="polite">{notice}</p>}
        {error && <p className="auth-error" role="alert">{error}</p>}
        {sourceWarnings.length > 0 && <p role="status">Source warnings: {sourceWarnings.join(", ")}</p>}
      </section>

      <section className="panel large-panel" style={{ marginTop: 16 }}>
        <div className="panel-head">
          <div><span className="eyebrow">PERSISTENT OWNER PIPELINE</span><h2>Saved opportunities</h2></div>
          <span className="badge">{items.length} RECORDS</span>
        </div>
        <div className="job-results" style={{ display: "grid", gap: 12 }}>
          {items.map(item => (
            <BrokerOpportunityCard
              key={item.id}
              opportunity={item}
              onUpdate={updateRow}
              onPrepare={prepare}
            />
          ))}
          {!items.length && <div className="empty">No opportunities saved yet. Start with remote graphic-design work or connect SearXNG to research suppliers and potential clients.</div>}
        </div>
        <p style={{ marginTop: 16, opacity: 0.8 }}>
          Verification rule: a search result is evidence of a published source response, not proof of the publisher's identity, current availability, buyer intent, supplier quality or guaranteed profit. Check eligibility and all commercial terms before contact or purchase.
        </p>
      </section>
    </>
  );
}
