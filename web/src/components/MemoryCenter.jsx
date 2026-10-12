import { useEffect, useMemo, useState } from "react";
import { createMemory, deleteMemory, getMemories, updateMemory } from "../api";

export default function MemoryCenter() {
  const [items, setItems] = useState([]);
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [status, setStatus] = useState("MEMORY READY");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const result = await getMemories();
      setItems(Array.isArray(result) ? result : []);
      setStatus("MEMORY REFRESHED");
    } catch (error) {
      setStatus("REFRESH FAILED · " + error.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter(item =>
      String(item.key || "").toLowerCase().includes(needle) ||
      String(item.value || "").toLowerCase().includes(needle)
    );
  }, [items, query]);

  async function submit(event) {
    event.preventDefault();
    const memoryKey = key.trim();
    const memoryValue = value.trim();
    if (!memoryKey || !memoryValue || busy) return;

    setBusy(true);
    setStatus("SAVING MEMORY...");
    try {
      await createMemory(memoryKey, memoryValue);
      setKey("");
      setValue("");
      const result = await getMemories();
      setItems(Array.isArray(result) ? result : []);
      setStatus("MEMORY SAVED");
    } catch (error) {
      setStatus("SAVE FAILED · " + error.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(id) {
    if (!editValue.trim() || busy) return;
    setBusy(true);
    setStatus("UPDATING MEMORY...");
    try {
      await updateMemory(id, editValue.trim());
      const result = await getMemories();
      setItems(Array.isArray(result) ? result : []);
      setEditingId(null);
      setEditValue("");
      setStatus("MEMORY UPDATED");
    } catch (error) {
      setStatus("UPDATE FAILED · " + error.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(item) {
    if (busy) return;
    if (!window.confirm(`Delete memory "${item.key}"? This cannot be undone.`)) return;
    setBusy(true);
    setStatus("DELETING MEMORY...");
    try {
      await deleteMemory(item.id);
      setItems(current => current.filter(entry => entry.id !== item.id));
      if (editingId === item.id) {
        setEditingId(null);
        setEditValue("");
      }
      setStatus("MEMORY DELETED");
    } catch (error) {
      setStatus("DELETE FAILED · " + error.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel large-panel memory-center">
      <div className="panel-head">
        <div>
          <span className="eyebrow">MEMORY CORE · OWNER-APPROVED RECORDS</span>
          <h2>Personal Memory</h2>
        </div>
        <div className="panel-head-actions">
          <span className="badge">{items.length} MEMORIES</span>
          <button type="button" className="mini-button" onClick={refresh} disabled={busy}>REFRESH</button>
        </div>
      </div>

      <form className="memory-create-form" onSubmit={submit}>
        <label htmlFor="memory-center-key">MEMORY KEY</label>
        <input id="memory-center-key" value={key} onChange={event => setKey(event.target.value)} maxLength={255} placeholder="Mfano: preferred_language" required />
        <label htmlFor="memory-center-value">MEMORY VALUE</label>
        <textarea id="memory-center-value" value={value} onChange={event => setValue(event.target.value)} maxLength={12000} placeholder="Kitu unachotaka MR AI ikumbuke..." required rows={3} />
        <button type="submit" className="primary-button" disabled={busy || !key.trim() || !value.trim()}>{busy ? "PLEASE WAIT..." : "SAVE MEMORY"}</button>
      </form>

      <div className="memory-toolbar">
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="SEARCH SAVED MEMORIES..." aria-label="Search memories" />
        <span>{visible.length} SHOWN</span>
      </div>
      <div className="tool-status" role="status" aria-live="polite">{status}</div>

      <div className="memory-center-list">
        {visible.map(item => (
          <article className="memory-center-row" key={item.id}>
            <div className="memory-center-main">
              <strong>{item.key}</strong>
              {editingId === item.id ? (
                <textarea aria-label={`Edit ${item.key}`} value={editValue} onChange={event => setEditValue(event.target.value)} rows={3} />
              ) : (
                <p>{item.value}</p>
              )}
              <small>RECORD #{item.id}</small>
            </div>
            <div className="memory-center-actions">
              {editingId === item.id ? (
                <>
                  <button type="button" className="primary-button" onClick={() => saveEdit(item.id)} disabled={busy || !editValue.trim()}>SAVE</button>
                  <button type="button" className="ghost-button" onClick={() => { setEditingId(null); setEditValue(""); }}>CANCEL</button>
                </>
              ) : (
                <button type="button" className="mini-button" onClick={() => { setEditingId(item.id); setEditValue(String(item.value || "")); }}>EDIT</button>
              )}
              <button type="button" className="ghost-button" onClick={() => remove(item)} disabled={busy}>DELETE</button>
            </div>
          </article>
        ))}
        {visible.length === 0 && (
          <div className="empty">{items.length ? "Hakuna memory inayolingana na search." : "Hakuna memory iliyohifadhiwa bado. Ongeza record hapo juu."}</div>
        )}
      </div>
      <p className="notice">Haya ni maandishi ya memory yaliyohifadhiwa kwenye akaunti yako. Usihifadhi password, API keys au taarifa za siri hapa.</p>
    </section>
  );
}
