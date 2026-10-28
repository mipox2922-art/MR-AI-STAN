import { useEffect, useState } from "react";
import {
  disconnectGmail,
  getGmailMessage,
  getGmailStatus,
  searchGmail,
  sendGmailMessage,
  replyToGmailMessage,
  startGmailConnect,
  getGmailAssistantStatus,
  getGmailAssistantDrafts,
  updateGmailAssistantConfig,
  runGmailAssistantNow,
} from "../api";

function StatusBadge({ value }) {
  return <span className={"gmail-status status-" + String(value || "unknown").toLowerCase()}>{value || "UNKNOWN"}</span>;
}

export default function GmailPanel() {
  const [status, setStatus] = useState(null);
  const [query, setQuery] = useState("in:inbox");
  const [messages, setMessages] = useState([]);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [composeTo, setComposeTo] = useState("");
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");
  const [replyToId, setReplyToId] = useState("");
  const [assistantStatus, setAssistantStatus] = useState(null);
  const [assistantDrafts, setAssistantDrafts] = useState([]);
  const [assistantBusy, setAssistantBusy] = useState(false);

  async function refreshStatus() {
    try {
      const value = await getGmailStatus();
      setStatus(value);
      return value;
    } catch (err) {
      setError(err.message);
      return null;
    }
  }

  async function refreshAssistant() {
    try {
      const [nextStatus, nextDrafts] = await Promise.all([
        getGmailAssistantStatus(),
        getGmailAssistantDrafts(),
      ]);
      setAssistantStatus(nextStatus);
      setAssistantDrafts(Array.isArray(nextDrafts?.items) ? nextDrafts.items : []);
    } catch (err) {
      setError(err.message || "Gmail VIP Assistant haipatikani.");
    }
  }

  useEffect(() => {
    let active = true;
    refreshStatus().then(value => {
      if (active && value?.connected) refreshAssistant();
    });
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      refreshStatus().then(value => {
        if (active && value?.connected) refreshAssistant();
      });
    }, 60000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  async function connect() {
    setBusy(true);
    setError("");
    // Open the tab synchronously in the user's click gesture; opening it after
    // awaiting the OAuth request can be blocked by popup protection.
    const popup = window.open("about:blank", "_blank");
    try {
      const result = await startGmailConnect();
      if (!result?.authorization_url) {
        popup?.close();
        throw new Error("Gmail OAuth did not return an authorization URL.");
      }
      if (popup) popup.location.href = result.authorization_url;
      else window.location.assign(result.authorization_url);
    } catch (err) {
      popup?.close();
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function search() {
    setBusy(true);
    setError("");
    setSelected(null);
    try {
      const result = await searchGmail(query, 20);
      setMessages(result.messages || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function openMessage(id) {
    setBusy(true);
    setError("");
    try {
      const result = await getGmailMessage(id);
      setSelected(result.message);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function setAssistantConfig(payload) {
    setAssistantBusy(true);
    setError("");
    setNotice("");
    try {
      const next = await updateGmailAssistantConfig(payload);
      setAssistantStatus(next);
      await refreshAssistant();
      setNotice(next.auto_send_enabled
        ? "Gmail VIP imewashwa. Majibu ya kawaida tu yanaweza kutumwa kiotomatiki; barua nyeti zitasubiri."
        : next.enabled
          ? "Gmail VIP inasoma na kuandaa rasimu. Kutuma kiotomatiki kumezimwa."
          : "Gmail VIP imesitishwa.");
    } catch (err) {
      setError(err.message || "Mipangilio ya Gmail VIP imeshindwa kuhifadhiwa.");
    } finally {
      setAssistantBusy(false);
    }
  }

  async function runAssistant() {
    setAssistantBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await runGmailAssistantNow();
      await refreshAssistant();
      await refreshStatus();
      const stats = result?.summary || {};
      setNotice("Gmail VIP: barua mpya " + (stats.messages_processed ?? result?.messages_processed ?? 0)
        + " · rasimu " + (stats.drafts_created ?? 0)
        + " · zilizotumwa kiotomatiki " + (stats.replies_sent ?? 0)
        + " · zinazohitaji ukaguzi " + (stats.needs_review ?? 0) + ".");
    } catch (err) {
      setError(err.message || "Gmail VIP haikuweza kukamilisha ukaguzi.");
    } finally {
      setAssistantBusy(false);
    }
  }

  async function useAssistantDraft(item) {
    if (!connected || busy || !item?.message_id) return;
    setBusy(true);
    setError("");
    try {
      const result = await getGmailMessage(item.message_id);
      setSelected(result.message);
      setReplyToId(item.message_id);
      setComposeTo("");
      setComposeSubject("");
      setComposeBody(item.follow_up_draft || item.reply_draft || "");
      setNotice("Rasimu imewekwa kwenye jibu. Ipitie kabla ya kutuma.");
    } catch (err) {
      setError(err.message || "Rasimu haikuweza kufunguliwa.");
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    setError("");
    try {
      await disconnectGmail();
      setMessages([]);
      setSelected(null);
      await refreshStatus();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }


  const connected = status?.connected === true;

  function beginReply() {
    if (!selected?.id) return;
    setReplyToId(selected.id);
    setComposeTo("");
    setComposeSubject("");
    setComposeBody("");
    setNotice(`Jibu limeandaliwa kwa: ${selected.subject || "barua iliyochaguliwa"}`);
    setError("");
  }

  function clearComposer() {
    setReplyToId("");
    setComposeTo("");
    setComposeSubject("");
    setComposeBody("");
    setNotice("");
    setError("");
  }

  async function sendComposedMessage() {
    if (!connected || busy) return;
    setError("");
    setNotice("");

    if (!composeBody.trim()) {
      setError("Andika ujumbe kabla ya kutuma.");
      return;
    }
    if (!replyToId && (!composeTo.trim() || !composeSubject.trim())) {
      setError("Weka email ya mpokeaji na subject.");
      return;
    }
    const target = replyToId
      ? (selected?.subject ? `jibu la "${selected.subject}"` : "jibu la barua iliyochaguliwa")
      : composeTo.trim();
    if (!window.confirm(`BOSS FERISI: Unathibitisha kutuma ${target}?\n\nUjumbe utatumwa kupitia Gmail yako.`)) {
      return;
    }

    setBusy(true);
    try {
      const result = replyToId
        ? await replyToGmailMessage(replyToId, composeBody.trim())
        : await sendGmailMessage({
            to: composeTo.trim(),
            subject: composeSubject.trim(),
            body: composeBody.trim(),
          });
      setNotice(result.status === "SENT"
        ? "Email imetumwa; Gmail imerudisha uthibitisho."
        : "Jibu limetumwa.");
      setComposeTo("");
      setComposeSubject("");
      setComposeBody("");
      setReplyToId("");
    } catch (err) {
      setError(err.message || "Email haikuweza kutumwa.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel large-panel gmail-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">COMMUNICATION</span>
          <h2>Gmail Command Channel</h2>
        </div>
        <StatusBadge value={connected ? "CONNECTED" : status?.configured ? "AUTHORIZATION REQUIRED" : status?.status} />
      </div>

      <div className="gmail-control-bar">
        <div className="gmail-connection-copy">
          <strong>GMAIL</strong>
          <span>
            {connected
              ? "Connected through scoped OAuth."
              : status?.configured
                ? "Backend is configured. User authorization is still required."
                : "OAuth client is not configured on the backend."}
          </span>
          {status?.scope?.length > 0 && (
            <small>SCOPES: {status.scope.join(", ")}</small>
          )}
        </div>
        <div className="gmail-actions">
          {!connected ? (
            <button className="primary-button" onClick={connect} disabled={busy || !status?.configured}>
              CONNECT GMAIL
            </button>
          ) : (
            <button className="ghost-button" onClick={disconnect} disabled={busy}>
              DISCONNECT
            </button>
          )}
        </div>
      </div>

      {connected && (
        <section className="gmail-assistant-box" style={{ marginTop: 14, marginBottom: 14, padding: 14, border: "1px solid var(--border, rgba(255,255,255,.15))", borderRadius: 10 }}>
          <div className="gmail-section-title">MR AI · GMAIL VIP ASSISTANT</div>
          <p style={{ margin: "8px 0", opacity: 0.85 }}>
            Inasoma barua mpya zisizosomwa, inaandaa majibu kwa AI, inahifadhi kazi za ufuatiliaji, na hukagua kama mtumaji amejibu.
          </p>
          <div className="gmail-actions" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className={assistantStatus?.enabled === false ? "ghost-button" : "primary-button"} disabled={assistantBusy} onClick={() => setAssistantConfig({ enabled: assistantStatus?.enabled === false })}>
              {assistantStatus?.enabled === false ? "WASHA GMAIL VIP" : "SIMAMISHA GMAIL VIP"}
            </button>
            <button className={assistantStatus?.auto_send_enabled ? "danger-button" : "ghost-button"} disabled={assistantBusy || assistantStatus?.enabled === false} onClick={() => {
              const next = !assistantStatus?.auto_send_enabled;
              if (next && !window.confirm("BOSS FERISI: Unaidhinisha MR AI kutuma kiotomatiki majibu yenye hatari ndogo tu? Barua zinazohusu fedha, mikataba, akaunti, afya, sheria, siri au ahadi zitabaki rasimu.")) return;
              setAssistantConfig({ auto_send_enabled: next });
            }}>
              {assistantStatus?.auto_send_enabled ? "AUTO-REPLY: ON" : "AUTO-REPLY: OFF"}
            </button>
            <button className="mini-button" disabled={assistantBusy || assistantStatus?.enabled === false} onClick={runAssistant}>
              {assistantBusy ? "INAKAGUA BARUA..." : "KAGUA INBOX SASA"}
            </button>
            <button className="mini-button" disabled={assistantBusy} onClick={refreshAssistant}>REFRESH VIP</button>
          </div>
          <div className="tool-status" style={{ marginTop: 10 }} role="status" aria-live="polite">
            {assistantStatus
              ? "VIP " + (assistantStatus.enabled ? "ACTIVE" : "PAUSED")
                + " · AUTO-SEND " + (assistantStatus.auto_send_enabled ? "ON" : "OFF")
                + " · RASIMU " + (assistantStatus.draft_count ?? assistantDrafts.length)
                + " · ZINAZOSUBIRI MAJIBU " + (assistantStatus.awaiting_reply ?? 0)
                + " · UCHUNGUZI WA MWISHO " + (assistantStatus.last_scan_at || "BADO")
                + " · SCHEDULER " + (assistantStatus.scheduler || "UNKNOWN")
              : "Inapakia hali ya Gmail VIP..."}
          </div>
          <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
            {assistantDrafts.slice(0, 12).map(item => (
              <article key={item.message_id} className="panel" style={{ padding: 12 }}>
                <div style={{ display: "flex", alignItems: "start", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <strong>{item.subject || "(Hakuna subject)"}</strong>
                    <p style={{ margin: "5px 0" }}>{item.from || "Mtumaji hajulikani"} · {item.status || "UNKNOWN"}</p>
                    <p style={{ margin: "5px 0", opacity: 0.85 }}>{item.summary || "Muhtasari haujapatikana."}</p>
                    {item.follow_up_note && <small>Ufuatiliaji: {item.follow_up_note}</small>}
                  </div>
                  {["DRAFT_READY", "FOLLOW_UP_DRAFT_READY"].includes(item.status) && (
                    <button className="mini-button" disabled={busy || assistantBusy} onClick={() => useAssistantDraft(item)}>TUMIA RASIMU</button>
                  )}
                </div>
                {item.reply_draft && item.status !== "REPLIED" && (
                  <details style={{ marginTop: 8 }}>
                    <summary style={{ cursor: "pointer" }}>Fungua rasimu</summary>
                    <textarea readOnly rows={4} value={item.follow_up_draft || item.reply_draft} style={{ width: "100%", marginTop: 8, resize: "vertical" }} />
                  </details>
                )}
              </article>
            ))}
            {!assistantDrafts.length && <div className="empty">Hakuna rasimu za Gmail VIP zilizohifadhiwa bado.</div>}
          </div>
          <small style={{ display: "block", marginTop: 8, opacity: 0.78 }}>
            AUTO-REPLY ni hiari na imezimwa hadi uidhinishe. Ujumbe nyeti na wenye maamuzi ya fedha/sheria hautatumwa kiotomatiki. Majibu ya mkono bado yanahitaji uthibitisho.
          </small>
        </section>
      )}

      <div className="gmail-search-row">
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder='Gmail search, e.g. "is:unread" or "from:boss@example.com"'
          disabled={!connected}
        />
        <button className="primary-button" onClick={search} disabled={busy || !connected}>
          SEARCH
        </button>
      </div>

      {error && <div className="auth-error">{error}</div>}

      <section className="gmail-composer" style={{ marginTop: 16, marginBottom: 16, padding: 14, border: "1px solid var(--border, rgba(255,255,255,.15))", borderRadius: 10 }}>
        <div className="gmail-section-title">
          {replyToId ? "REPLY TO SELECTED MESSAGE" : "COMPOSE EMAIL"}
        </div>
        {!connected && <p className="empty">Unganisha Gmail kwanza ili kuandika na kutuma barua.</p>}
        {replyToId && selected && (
          <p className="empty">Unajibu: {selected.subject || "(no subject)"} · {selected.from || "sender unknown"}</p>
        )}
        {!replyToId && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10, marginTop: 10 }}>
            <label style={{ display: "grid", gap: 5 }}>
              <span className="eyebrow">TO</span>
              <input type="email" value={composeTo} onChange={event => setComposeTo(event.target.value)} placeholder="recipient@example.com" disabled={!connected || busy} />
            </label>
            <label style={{ display: "grid", gap: 5 }}>
              <span className="eyebrow">SUBJECT</span>
              <input value={composeSubject} onChange={event => setComposeSubject(event.target.value)} placeholder="Subject" disabled={!connected || busy} />
            </label>
          </div>
        )}
        <label style={{ display: "grid", gap: 5, marginTop: 10 }}>
          <span className="eyebrow">MESSAGE</span>
          <textarea rows={5} value={composeBody} onChange={event => setComposeBody(event.target.value)} placeholder="Andika barua yako hapa..." disabled={!connected || busy} />
        </label>
        <div className="gmail-actions" style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="primary-button" onClick={sendComposedMessage} disabled={!connected || busy || !composeBody.trim()}>
            {busy ? "INATUMA..." : replyToId ? "SEND REPLY" : "SEND EMAIL"}
          </button>
          <button className="ghost-button" onClick={clearComposer} disabled={busy}>CLEAR</button>
        </div>
        {notice && <p className="tool-status" role="status" aria-live="polite">{notice}</p>}
        <small style={{ display: "block", marginTop: 8, opacity: 0.78 }}>
          Kutuma barua kunahitaji Gmail OAuth yenye send permission. Kila barua hapa inahitaji uthibitisho wako kwa kubonyeza kitufe.
        </small>
      </section>

      <div className="gmail-layout">
        <div className="gmail-message-list">
          <div className="gmail-section-title">
            RESULTS <span>{messages.length}</span>
          </div>
          {messages.map(message => (
            <button
              className={"gmail-message" + (selected?.id === message.id ? " selected" : "")}
              key={message.id}
              onClick={() => openMessage(message.id)}
            >
              <strong>{message.subject || "(no subject)"}</strong>
              <span>{message.from || "Unknown sender"}</span>
              <small>{message.snippet || ""}</small>
            </button>
          ))}
          {connected && messages.length === 0 && (
            <div className="empty">No results loaded. Run a Gmail search.</div>
          )}
          {!connected && (
            <div className="empty">Connect Gmail to access mailbox search.</div>
          )}
        </div>

        <div className="gmail-reader">
          <div className="gmail-section-title">MESSAGE READER</div>
          {selected ? (
            <>
              <div className="gmail-reader-head">
                <h3>{selected.subject || "(no subject)"}</h3>
                <span>{selected.date || "--"}</span>
                <small>FROM {selected.from || "--"}</small>
                <small>TO {selected.to || "--"}</small>
              </div>
              <pre>{selected.body_text || selected.snippet || "No readable text body."}</pre>
              <div style={{ marginTop: 10 }}>
                <button className="primary-button" type="button" onClick={beginReply} disabled={busy || !connected}>REPLY TO THIS MESSAGE</button>
              </div>
            </>
          ) : (
            <div className="empty">Select a message to read its verified content.</div>
          )}
        </div>
      </div>
    </section>
  );
}
