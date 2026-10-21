import { useEffect, useRef, useState } from "react";
import "./style.css";

type Rule = { ok: boolean; rule: string; detail: string };
type RecordFields = Record<string, string | number | string[] | null>;
type Document = {
  id: string; name: string; state: string; kind: string; version: number; error: string | null;
  record?: RecordFields; doc_type?: string; type_confirmed?: boolean; manual_note?: string;
  checks?: Rule[]; text?: string; ocr_used?: boolean; pages?: number;
  prediction?: { label: string; confidence: number };
};
const fields = ["vendor", "number", "date", "due_date", "currency", "subtotal", "tax", "total", "line_total"];
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof error.detail === "string" ? error.detail : JSON.stringify(error.detail));
  }
  return response.json() as Promise<T>;
}

export function App(): JSX.Element {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const selectedRef = useRef<string | null>(null);
  const docRef = useRef<Document | null>(null);
  const [doc, setDoc] = useState<Document | null>(null);
  const [record, setRecord] = useState<RecordFields>({});
  const [type, setType] = useState("invoice");
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [history, setHistory] = useState<{ seq: number; action: string; created: number; details: unknown }[]>([]);
  const [modelNote, setModelNote] = useState("");

  async function refreshList() { setDocuments(await api<Document[]>("/documents")); }
  function load(value: Document) {
    const current = docRef.current;
    if (current?.id === value.id && (current.version > value.version || (current.version === value.version && current.state === value.state))) return;
    docRef.current = value;
    setDoc(value); setRecord(value.record ?? {}); setType(value.doc_type ?? "invoice");
    setConfirmed(value.type_confirmed ?? false); setNote(value.manual_note ?? ""); setDirty(false);
  }
  useEffect(() => {
    void refreshList().catch(e => setError(String(e)));
    void api<{ model_note: string }>("/health").then(h => setModelNote(h.model_note)).catch(e => setError(String(e)));
    const timer = setInterval(() => { void refreshList().catch(e => setError(String(e))); }, 900);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!selected) return;
    let alive = true;
    void api<Document>(`/documents/${selected}`).then(value => { if (alive && selectedRef.current === value.id) load(value); }).catch(e => setError(String(e)));
    return () => { alive = false; };
  }, [selected]);
  useEffect(() => {
    if (!doc || !["queued", "processing"].includes(doc.state)) return;
    let alive = true;
    let inFlight = false;
    const timer = setInterval(() => {
      if (inFlight) return;
      inFlight = true;
      void api<Document>(`/documents/${doc.id}`).then(value => {
        if (alive && selectedRef.current === value.id) load(value);
      }).catch(e => { if (alive) setError(String(e)); }).finally(() => { inFlight = false; });
    }, 500);
    return () => { alive = false; clearInterval(timer); };
  }, [doc?.id, doc?.state]);
  useEffect(() => {
    let alive = true;
    if (doc) void api<typeof history>(`/documents/${doc.id}/history`).then(value => {
      if (alive && selectedRef.current === doc.id) setHistory(value);
    }).catch(e => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [doc?.id, doc?.version]);

  async function upload(file: File) {
    setBusy(true); setError("");
    try {
      const form = new FormData(); form.append("file", file);
      const value = await api<Document>("/documents", { method: "POST", body: form });
      selectedRef.current = value.id; load(value); setSelected(value.id); await refreshList();
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function mutate(action: "review" | "approve" | "reject" | "reopen") {
    if (!doc) return;
    setBusy(true); setError("");
    try {
      const body = { version: doc.version, request_id: crypto.randomUUID(), note,
        ...(action === "review" ? { record, doc_type: type, type_confirmed: confirmed } : {}) };
      load(await api<Document>(`/documents/${doc.id}/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }));
      await refreshList();
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function exportRecords(format: "json" | "csv") {
    setError("");
    try {
      const response = await fetch(`/api/exports/${format}`, { method: "POST" });
      if (!response.ok) throw new Error("Export failed");
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a"); a.href = url; a.download = `approved-records.${format}`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(String(e)); }
  }
  const editable = !!doc && ["review", "ready"].includes(doc.state);
  const failures = doc?.checks?.filter(c => !c.ok) ?? [];
  return <main>
    <header><p className="eyebrow">LOCAL DOCUMENT WORKSPACE</p><h1>Intake & review</h1>
      <p>Compare the original, correct extracted fields, then make an explicit decision.</p>
      <details><summary>Classifier limits and local use</summary><p>{modelNote}</p><p>Single user, loopback server, no authentication. Do not expose this service to a network. Only invoices have accounting automation; other types require an explicit manual review note.</p></details>
    </header>
    <div className="toolbar"><label>Upload document <input aria-label="Upload document" type="file" accept=".txt,.pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff" disabled={busy} onChange={e => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} /></label>
      <span>8 MB Â· up to 10 pages Â· UTF-8 text, PDF or image</span>
      <button onClick={() => void exportRecords("json")}>Export approved JSON</button><button onClick={() => void exportRecords("csv")}>Export approved CSV</button>
    </div>
    {error && <p role="alert" className="error">{error} <button onClick={() => { if (selected) void api<Document>(`/documents/${selected}`).then(load); }}>Reload selected document</button></p>}
    <div className="workspace"><aside aria-label="Document list"><h2>Documents <small>{documents.length}</small></h2>
      {documents.length === 0 && <p>No documents yet. Choose a sample to begin.</p>}
      {documents.map(d => <button className={`document ${d.id === selected ? "selected" : ""}`} key={d.id} disabled={busy} onClick={() => { selectedRef.current = d.id; setSelected(d.id); setError(""); }}><strong>{d.name}</strong><span className={`status ${d.state}`}>{d.state}</span></button>)}
    </aside>
    {!doc ? <section className="empty"><h2>Your review starts here</h2><p>Upload an original or select a document from the list. Originals and review history survive restart.</p></section> : <article>
      <div className="title"><h2>{doc.name}</h2><span data-testid="document-state" className={`status ${doc.state}`}>{doc.state}</span></div>
      {["queued", "processing"].includes(doc.state) && <p role="status">{doc.state === "queued" ? "Queued for a background workerâ€¦" : "Reading pages and extracting fieldsâ€¦"}</p>}
      {doc.error && <p className="error">{doc.error}</p>}
      <div className="review"><section><h3>Original</h3><a href={`/api/documents/${doc.id}/original`} target="_blank" rel="noreferrer">Open original</a>
        {doc.kind === "image" && doc.state !== "failed" ? <img alt="Original document" src={`/api/documents/${doc.id}/original`} /> : doc.kind === "application/pdf" ? <iframe title="Original document" src={`/api/documents/${doc.id}/original`} /> : <pre aria-label="Original text">{doc.text ?? "Text will appear after processing."}</pre>}
        {doc.text && doc.kind !== "text/plain" && <details><summary>Extracted text</summary><pre>{doc.text}</pre></details>}
      </section>
      {doc.record && <section><h3>Review fields</h3><p className="muted">Suggested {doc.prediction?.label} Â· {Math.round((doc.prediction?.confidence ?? 0)*100)}% confidence Â· {doc.ocr_used ? "OCR used" : "embedded / uploaded text"} Â· {doc.pages} page(s)</p>
        <fieldset disabled={!editable || busy}><label>Document type<select aria-label="Document type" value={type} onChange={e => { setType(e.target.value); setDirty(true); }}>{["invoice", "receipt", "statement", "contract", "credit_note", "other"].map(t => <option key={t}>{t}</option>)}</select></label>
          <div className="fields">{fields.map(field => <label key={field}>{field.replaceAll("_", " ")}<input aria-label={field} value={String(record[field] ?? "")} onChange={e => { setRecord({ ...record, [field]: e.target.value || null }); setDirty(true); }} /></label>)}</div>
          <label className="checkbox"><input type="checkbox" checked={confirmed} onChange={e => { setConfirmed(e.target.checked); setDirty(true); }} />I checked the document type against the original</label>
          <label>Review / rejection note<textarea aria-label="Review note" value={note} onChange={e => { setNote(e.target.value); setDirty(true); }} /></label>
          <p className="muted">Amounts use two decimal places and an explicit currency. Date: YYYY-MM-DD. For manual types, confirm the type and enter a note of at least 10 characters.</p>
          <button className="primary" onClick={() => void mutate("review")}>Save corrections & revalidate</button>
        </fieldset>
        <div className="checks"><h3>Validation Â· {failures.length} failed</h3>{doc.checks?.map(c => <div className={c.ok ? "check pass" : "check fail"} key={c.rule}><strong>{c.ok ? "Pass" : "Check"}: {c.rule}</strong><p>{c.detail}</p></div>)}</div>
        {editable && <div className="decisions"><button className="primary" disabled={busy || dirty || doc.state !== "ready"} onClick={() => void mutate("approve")}>Approve document</button><button disabled={busy} onClick={() => void mutate("reject")}>Reject document</button>{dirty && <p>Save and revalidate your changes before approval.</p>}</div>}
        {doc.state === "approved" && <p className="success">Approved. This record is included in exports; the decision is final.</p>}
        {doc.state === "rejected" && <div><p>Rejected. Excluded from exports. Reopen this original to recover a mistaken rejection.</p><label>Reopen reason<input aria-label="Reopen reason" value={note} onChange={e => setNote(e.target.value)} /></label><button onClick={() => void mutate("reopen")}>Reopen for review</button></div>}
      </section>}
      </div><details className="history"><summary>Review history ({history.length})</summary><ol>{history.map(h => <li key={h.seq}><strong>{h.action}</strong> Â· {new Date(h.created*1000).toLocaleString()}<pre>{JSON.stringify(h.details, null, 2)}</pre></li>)}</ol></details>
    </article>}
    </div>
  </main>;
}
