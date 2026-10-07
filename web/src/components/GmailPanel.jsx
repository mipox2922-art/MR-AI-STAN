import { useEffect, useState } from "react";
import {
  disconnectGmail,
  getGmailMessage,
  getGmailStatus,
  searchGmail,
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
    try {
      const result = await startGmailConnect();
      window.open(result.authorization_url, "_blank", "noopener,noreferrer");
    } catch (err) {
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
            </>
          ) : (
            <div className="empty">Select a message to read its verified content.</div>
          )}
        </div>
      </div>
    </section>
  );
}
