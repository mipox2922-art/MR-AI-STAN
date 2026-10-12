import { useEffect, useMemo, useState } from "react";
import { createMemory, deleteMemory, getMemories, updateMemory } from "../api";

export default function MemoryPanel() {
  const [memories, setMemories] = useState([]);
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("LOADING MEMORY");

  async function load() {
    try {
      const result = await getMemories();
      setMemories(Array.isArray(result) ? result : []);
      setStatus("MEMORY LOADED");
    } catch (error) {
      setStatus("LOAD FAILED · " + error.message);
    }
  }

  useEffect(() => { load(); }, []);

  const visible = useMemo(() => memories.filter(item =>
    [item.key, item.value].join(" ").toLowerCase().includes(query.trim().toLowerCase())
  ), [memories, query]);

  async function submit(event) {
    event.preventDefault();
    if (!key.trim() || !value.trim() || busy) return;
    setBusy(true);
    setStatus("SAVING MEMORY");
    try {
      await createMemory(key.trim(), value.trim());
      setKey("");
      setValue("");
      await load();
      setStatus("MEMORY SAVED");
    } catch (error) {
      setStatus("SAVE FAILED · " + error.message);
    } finally {
      setBusy(false);
    }
  }

  function beginEdit(item) {
    setEditingId(item.id);
    setEditValue(item.value || "");
    setStatus("EDITING · " + item.key);
  }

  async function saveEdit(item) {
    if (!editValue.trim() || busy) {
      if (!editValue.trim()) setStatus("MEMORY VALUE IS REQUIRED");
      return;
    }
    setBusy(true);
    setStatus("UPDATING MEMORY");
    try {
      await updateMemory(item.id, editValue.trim());
      setEditingId(null);
      setEditValue("");
      await load();
      setStatus("MEMORY UPDATED");
    } catch (error) {
      setStatus("UPDATE FAILED · " + error.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(item) {
    if (busy) return;
    if (!window.confirm("Delete memory “" + item.key + "”? This cannot be undone.")) return;
    setBusy(true);
    setStatus("DELETING MEMORY");
    try {
      await deleteMemory(item.id);
      if (editingId === item.id) {
        setEditingId(null);
        setEditValue("");
      }
      await load();
      setStatus("MEMORY DELETED");
    } catch (error) {
      setStatus("DELETE FAILED · " + error.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel large-panel memory-manager">
      <div className="panel-head">
        <div><span className="eyebrow">MEMORY CORE</span><h2>User-approved memory</h2></div>
        <button type="button" className="mini-button" onClick={load} disabled={busy}>REFRESH</button>
      </div>

      <p className="notice">Store useful preferences and project facts you explicitly approve. Memory values are visible in this signed-in workspace; do not save passwords, API keys, or other secrets here.</p>

      <form className="memory-create-form" onSubmit={submit}>
        <label>MEMORY KEY
          <input value={key} onChange={event => setKey(event.target.value)} maxLength={255} required placeholder="e.g. project_preferences" />
        </label>
        <label>MEMORY VALUE
          <textarea value={value} onChange={event => setValue(event.target.value)} required rows={3} placeholder="Write the fact or preference to remember..." />
        </label>
        <button type="submit" className="primary-button" disabled={busy || !key.trim() || !value.trim()}>{busy ? "WORKING..." : "SAVE MEMORY"}</button>
      </form>

      <div className="memory-list-toolbar">
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search memory..." aria-label="Search memory" />
        <span>{visible.length} / {memories.length} RECORDS</span>
      </div>
      <div className="tool-status" role="status" aria-live="polite">{status}</div>

      <div className="memory-record-list">
        {visible.map(item => (
          <article className="memory-record" key={item.id}>
            <div className="memory-record-head">
              <div><span>MEMORY #{item.id}</span><strong>{item.key}</strong></div>
              <div className="memory-record-actions">
                {editingId === item.id ? (
                  <>
                    <button type="button" className="mini-button" onClick={() => saveEdit(item)} disabled={busy}>SAVE</button>
                    <button type="button" className="ghost-button" onClick={() => { setEditingId(null); setEditValue(""); }} disabled={busy}>CANCEL</button>
                  </>
                ) : (
                  <button type="button" className="mini-button" onClick={() => beginEdit(item)} disabled={busy}>EDIT</button>
                )}
                <button type="button" className="ghost-button" onClick={() => remove(item)} disabled={busy}>DELETE</button>
              </div>
            </div>
            {editingId === item.id
              ? <textarea value={editValue} onChange={event => setEditValue(event.target.value)} rows={3} aria-label={"Edit memory " + item.id} />
              : <p className="memory-record-value">{item.value}</p>}
            <small>UPDATED {item.updated_at || item.created_at ? new Date(item.updated_at || item.created_at).toLocaleString("en-GB") : "—"}</small>
          </article>
        ))}
        {visible.length === 0 && <div className="empty">{memories.length ? "No memory records match this search." : "No saved memories yet. Add the first approved memory above."}</div>}
      </div>
    </section>
  );
}
