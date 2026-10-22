import { useEffect, useState } from "react";
import {
  disconnectGmail,
  getGmailMessage,
  getGmailStatus,
  searchGmail,
  sendGmailMessage,
  replyToGmailMessage,
  startGmailConnect,
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

  useEffect(() => {
    refreshStatus();
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
        <StatusBadge value={status?.status} />
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
