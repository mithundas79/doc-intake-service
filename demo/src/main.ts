import { samples, type Fields, type Sample } from "./fixtures";
import "./style.css";

type Status = "review" | "ready" | "approved" | "rejected";
type Review = { fields: Fields; type: string; confirmed: boolean; note: string };
type Check = { ok: boolean; name: string; detail: string };
type State = { sample: Sample; saved: Review; draft: Review; status: Status; checks: Check[]; dirty: boolean; rejectionReason?: string };
type Audit = { action: string; sample: string; detail: string; at: string };

const root = document.querySelector<HTMLDivElement>("#app")!;
const sourceURL = "https://github.com/mithundas79/doc-intake-service";
const installURL = `${sourceURL}/blob/feature/persistent-document-review/README.md#install-the-complete-local-application`;
const labels: Record<keyof Fields, string> = { vendor: "Vendor / counterparty", number: "Document number", date: "Date", currency: "Currency", subtotal: "Subtotal", tax: "Tax", total: "Total", line_total: "Line total" };
let states: State[];
let selected = "incorrect-total";
let audit: Audit[];
let notice = "Start with the incorrect total. Your changes stay only in this tab.";
let error = "";

function escape(value: string): string {
  return value.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}
function cents(value: string): bigint | null {
  // Deliberately small sample validator, not a port of the Python rule engine.
  if (!/^\d{1,10}(?:\.\d{1,2})?$/.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  const amount = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  return amount <= 999999999999n ? amount : null;
}
function validate(review: Review): Check[] {
  const fields = review.fields;
  const parsedDate = new Date(`${fields.date}T00:00:00Z`);
  const dateOK = /^\d{4}-\d{2}-\d{2}$/.test(fields.date) && !Number.isNaN(parsedDate.valueOf()) && parsedDate.toISOString().slice(0, 10) === fields.date;
  const checks: Check[] = [
    { ok: !!fields.vendor.trim(), name: "Counterparty recorded", detail: "Check the vendor or counterparty against the original." },
    { ok: dateOK, name: "Unambiguous date", detail: "Use a valid YYYY-MM-DD date." },
    { ok: ["USD", "EUR", "GBP", "INR"].includes(fields.currency), name: "Explicit currency", detail: "Choose USD, EUR, GBP or INR; this preview does not convert currencies." },
  ];
  if (review.type !== "invoice") {
    checks.push({ ok: review.confirmed && review.note.trim().length >= 10, name: "Manual review recorded", detail: "Confirm the type and add a note of at least 10 characters. No invoice arithmetic is applied." });
    return checks;
  }
  const subtotal = cents(fields.subtotal), tax = cents(fields.tax), total = cents(fields.total), lines = cents(fields.line_total);
  checks.push(
    { ok: !!fields.number.trim(), name: "Invoice number recorded", detail: "Verify the document number against the original." },
    { ok: [subtotal, tax, total, lines].every(v => v !== null), name: "Decimal amounts complete", detail: "Use nonnegative dot-decimal amounts with at most two decimal places." },
    { ok: subtotal !== null && tax !== null && total !== null && subtotal + tax === total, name: "Subtotal + tax = total", detail: `${fields.subtotal || "?"} + ${fields.tax || "?"} must equal ${fields.total || "?"}. For the Ridgeway sample, the corrected total is 329.84.` },
    { ok: lines !== null && subtotal !== null && lines === subtotal, name: "Line sum = subtotal", detail: "Verify the prepared line sum against the original line amounts." },
  );
  return checks;
}
function initialize(): void {
  states = samples.map(sample => {
    const saved = { fields: { ...sample.fields }, type: sample.type, confirmed: false, note: "" };
    const checks = validate(saved);
    return { sample, saved, draft: structuredClone(saved), status: checks.every(c => c.ok) ? "ready" : "review", checks, dirty: false };
  });
  audit = [{ action: "Prepared samples loaded", sample: "All samples", detail: "Fictional text and prepared field snapshots; no OCR, classifier or API call.", at: new Date().toISOString() }];
}
function current(): State { return states.find(s => s.sample.id === selected)!; }
function final(state: State): boolean { return ["approved", "rejected"].includes(state.status); }
function event(action: string, detail: string, sample = current().sample.name): void {
  audit.push({ action, sample, detail, at: new Date().toISOString() });
}
function announce(message: string, failure = false): void {
  notice = failure ? "" : message;
  error = failure ? message : "";
}
function syncButtons(): void {
  const state = current();
  document.querySelector<HTMLButtonElement>("#approve")!.disabled = final(state) || state.dirty || state.status !== "ready";
  document.querySelector<HTMLElement>("#unsaved")!.textContent = state.dirty ? "Unsaved changes. Save and revalidate before approval." : "Checks below describe the last saved sample fields.";
}
function render(focusSelector?: string): void {
  const previous = document.activeElement as HTMLElement | null;
  const previousSelector = previous && root.contains(previous)
    ? previous.id ? `#${CSS.escape(previous.id)}`
      : previous.dataset.sample ? `[data-sample="${CSS.escape(previous.dataset.sample)}"]`
        : previous.getAttribute("name") ? `[name="${CSS.escape(previous.getAttribute("name")!)}"]` : null
    : null;
  const state = current(), review = state.draft;
  const approved = states.filter(s => s.status === "approved").length;
  const decided = states.filter(final).length;
  root.innerHTML = `
    <a class="skip-link" href="#review-workspace">Skip to sample review</a>
    <main class="page">
      <nav class="top-nav" aria-label="Main"><a class="brand" href="./">DOC INTAKE <span>/ SERVICE</span></a><div><a href="#walkthrough">How to use this preview</a><a href="${installURL}">Install the local app <span aria-hidden="true">&#8599;</span></a></div></nav>
      <header class="hero">
        <div><span class="sample-badge">GUIDED SAMPLE PREVIEW</span><h1>Review before<br />you approve.</h1><p>Compare an original with proposed fields, fix a mismatch, and make the final decision yourself.</p></div>
        <div class="boundary"><h2>Three fictional samples. Your decisions.</h2><p>This static page uses prepared text and field snapshots. It runs <strong>no Python API, native OCR, live classifier or SQLite</strong>.</p><p>Edits and activity live in this tab's memory. Reload or reset clears them. Use the local application for real uploads and durable review.</p><a href="#capabilities">Compare preview and local app</a></div>
      </header>
      <section class="walkthrough" id="walkthrough" aria-labelledby="guide-title"><div class="section-heading"><div><p class="eyebrow">TRY THE WORKFLOW</p><h2 id="guide-title">A two-minute guided review</h2></div><button id="reset" class="subtle">Reset all samples</button></div>
        <ol class="steps"><li><span>01</span><div><strong>Find the mismatch</strong><p>In Incorrect total, 304.00 + 25.84 is 329.84, not the original 349.84.</p></div></li><li><span>02</span><div><strong>Correct, then revalidate</strong><p>Enter 329.84 in Total. Save &amp; revalidate changes the status to ready.</p></div></li><li><span>03</span><div><strong>Approve, then export</strong><p>Click Approve sample. Only approved samples appear in downloaded JSON or CSV.</p></div></li></ol>
        <p class="guide-extra">Next: choose <strong>Manual review</strong>, confirm the type and add a note such as "Read the terms and verified the parties and date". Save, then decide. The valid invoice starts ready and still needs explicit approval.</p>
      </section>
      <div class="feedback"><p id="notice" role="status" aria-live="polite">${escape(notice)}</p><p id="error" role="alert">${escape(error)}</p></div>
      <section class="workspace" id="review-workspace" aria-label="Sample review workspace">
        <aside class="sample-list"><p class="eyebrow">PREPARED DOCUMENTS</p><h2>Choose a sample</h2>${states.map(s => `<button class="sample ${s === state ? "selected" : ""}" data-sample="${s.sample.id}" aria-label="${s.sample.name} sample" aria-pressed="${s === state}"><strong>${s.sample.name}</strong><span>${s.sample.filename}</span><em class="status ${s.status}">${s.status}</em></button>`).join("")}
          <div class="decision-progress"><label for="progress">${decided} of 3 decisions made</label><progress id="progress" max="3" value="${decided}"></progress><p>Ready is not approved.</p></div>
        </aside>
        <article class="review-panel"><div class="review-heading"><div><p class="eyebrow">${state.sample.type === "invoice" ? "INVOICE SAMPLE" : "MANUAL-ONLY SAMPLE"}</p><h2>${state.sample.name}</h2></div><span id="document-state" tabindex="-1" aria-label="Sample status: ${state.status}" class="status ${state.status}">${state.status}</span></div>
          <p class="expected"><strong>Expected outcome:</strong> ${escape(state.sample.expected)}</p>
          <div class="comparison"><section class="original"><div class="panel-heading"><h3>Original text</h3><button id="original-download" class="text-button">Download TXT</button></div><p class="caption">Unchanged fictional source document</p><pre id="original-text">${escape(state.sample.original)}</pre></section>
            <section><h3>Review the prepared fields</h3><p class="caption">Edit a snapshot. No extraction or classification runs here.</p><form id="review-form"><fieldset ${final(state) ? "disabled" : ""}>
              <label>Document type<select id="doc-type" name="type"><option value="invoice" ${review.type === "invoice" ? "selected" : ""}>invoice</option><option value="contract" ${review.type === "contract" ? "selected" : ""}>contract</option><option value="statement" ${review.type === "statement" ? "selected" : ""}>statement</option><option value="receipt" ${review.type === "receipt" ? "selected" : ""}>receipt</option><option value="other" ${review.type === "other" ? "selected" : ""}>other</option></select></label>
              <div class="fields">${(Object.keys(labels) as (keyof Fields)[]).map(key => `<label class="${key === "vendor" ? "wide" : ""}">${labels[key]}<input name="${key}" value="${escape(review.fields[key])}" ${["subtotal", "tax", "total", "line_total"].includes(key) ? 'inputmode="decimal"' : ""} ${key === "total" ? 'aria-describedby="total-hint"' : ""} /></label>`).join("")}</div>
              <p id="total-hint" class="caption">For the incorrect-total sample, enter <strong>329.84</strong>.</p>
              <label class="checkbox"><input type="checkbox" name="confirmed" ${review.confirmed ? "checked" : ""} />I checked the document type against the original</label>
              <label>Review / rejection note<textarea id="review-note" name="note" rows="3">${escape(review.note)}</textarea></label>
              <p class="caption">Manual types require confirmation and a note of at least 10 characters. Rejection requires a reason of at least 3 characters and discards unsaved field/type edits.</p><button id="save" class="primary" type="submit">Save &amp; revalidate</button>
            </fieldset></form><p id="unsaved" class="caption"></p></section>
          </div>
          <section class="validation" aria-label="Sample validation"><div class="panel-heading"><h3>Saved validation checks</h3><span>${state.checks.filter(c => !c.ok).length} failed</span></div><p class="caption">These small client-side sample checks illustrate the workflow; the Python backend remains the local app's authority. No duplicate check is simulated.</p><div class="checks">${state.checks.map(c => `<div class="check ${c.ok ? "pass" : "fail"}"><span>${c.ok ? "PASS" : "CHECK"}</span><div><strong>${escape(c.name)}</strong><p>${escape(c.detail)}</p></div></div>`).join("")}</div></section>
          <div class="decision-bar"><div><button id="approve" class="primary">Approve sample</button><button id="reject" ${final(state) ? "disabled" : ""}>Reject sample</button></div><p>${state.status === "approved" ? "Approved explicitly. This sample is included in exports." : state.status === "rejected" ? `Rejected: ${escape(state.rejectionReason || "")}. Excluded from exports. Unsaved field/type edits were discarded; the saved fields remain above. Reset to try again.` : "Review the source yourself. A passing check never approves a sample."}</p></div>
        </article>
      </section>
      <section class="outputs"><div class="export-panel"><p class="eyebrow">APPROVED RECORDS ONLY</p><h2>Take the sample result with you</h2><p><strong id="approved-count">${approved}</strong> approved sample${approved === 1 ? "" : "s"} in the export. With none approved, downloads contain an empty JSON array or a CSV header.</p><div class="button-row"><button id="export-json">Download approved JSON</button><button id="export-csv">Download approved CSV</button></div><p class="caption">Downloads are generated in your browser with safe fixed filenames and escaped CSV formula cells. Reset cannot remove files you have already downloaded.</p></div>
        <div class="audit-panel"><p class="eyebrow">IN-MEMORY ACTIVITY</p><h2>See what changed</h2><p class="caption">An illustrative activity preview, not the local application's durable audit.</p><ol id="audit" reversed>${[...audit].reverse().map(item => `<li><strong>${escape(item.action)}</strong><span>${escape(item.sample)}</span><p>${escape(item.detail)}</p></li>`).join("")}</ol></div>
      </section>
      <section id="capabilities" class="capabilities"><p class="eyebrow">CHOOSE THE RIGHT ENVIRONMENT</p><h2>The preview explains. The local app processes.</h2><div class="table-scroll"><table><caption>Capabilities of this static preview and the complete local application</caption><thead><tr><th scope="col">Capability</th><th scope="col">This sample preview</th><th scope="col">Local Python + React app</th></tr></thead><tbody><tr><th scope="row">Input</th><td>Three bundled fictional TXT samples</td><td>Your TXT, image and multipage PDF uploads</td></tr><tr><th scope="row">OCR / classification</th><td>Prepared snapshots; neither runs here</td><td>Native Tesseract + fallible trained classifier</td></tr><tr><th scope="row">Review / exports</th><td>Client-side illustration and downloads</td><td>Backend-validated, audited decisions and exports</td></tr><tr><th scope="row">History / duplicates</th><td>Tab memory only; no durable duplicate detection</td><td>Transactional SQLite and durable duplicate identity</td></tr><tr><th scope="row">After reload</th><td>Samples reset</td><td>Originals and review decisions persist</td></tr></tbody></table></div><p>No data is uploaded by this preview. To process your own documents, <a href="${installURL}">follow the local installation and test instructions</a>. The complete app is for one trusted user on loopback, not a production multi-user service.</p></section>
      <footer><span>Fictional samples and project code: MIT. No real-world accuracy claim.</span><a href="${sourceURL}/tree/feature/persistent-document-review/demo">Demo source</a><a href="${installURL}">Install &amp; test</a></footer>
    </main>`;
  bind();
  syncButtons();
  const selector = focusSelector ?? previousSelector;
  if (selector) {
    const next = document.querySelector<HTMLElement>(selector);
    if (next && !(next as HTMLButtonElement).disabled) next.focus({ preventScroll: true });
    else document.querySelector<HTMLElement>("#document-state")!.focus();
  }
}
function download(filename: string, type: string, contents: string): void {
  const url = URL.createObjectURL(new Blob([contents], { type }));
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportedRecords(): object[] {
  return states.filter(s => s.status === "approved").map(s => ({ id: s.sample.id, doc_type: s.saved.type, ...Object.fromEntries(Object.entries(s.saved.fields).map(([key, value]) => [key, value || null])) }));
}
function csvCell(value: unknown): string {
  let text = value == null ? "" : String(value);
  if (/^[\t\r\n]/.test(text) || /^[=+\-@]/.test(text.trimStart())) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
function exportSamples(format: "json" | "csv"): void {
  const records = exportedRecords();
  let contents = JSON.stringify(records, null, 2);
  if (format === "csv") {
    const columns = ["id", "doc_type", ...Object.keys(labels)];
    contents = "\uFEFF" + [columns, ...records.map(record => columns.map(key => (record as Record<string, unknown>)[key]))].map(row => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
  }
  event(`Exported ${format.toUpperCase()}`, `${records.length} approved sample(s) included.`, "All samples");
  download(`approved-sample-records.${format}`, format === "json" ? "application/json" : "text/csv;charset=utf-8", contents);
  announce(`Downloaded ${records.length} approved sample(s) as ${format.toUpperCase()}.`);
  render();
}
function bind(): void {
  document.querySelectorAll<HTMLButtonElement>("[data-sample]").forEach(button => button.onclick = () => {
    selected = button.dataset.sample!; announce(current().sample.expected); render();
  });
  document.querySelector<HTMLButtonElement>("#reset")!.onclick = () => {
    initialize(); selected = "incorrect-total"; announce("All sample edits, decisions and activity reset. Start with total 349.84 again."); render();
  };
  const form = document.querySelector<HTMLFormElement>("#review-form")!;
  form.oninput = () => {
    const state = current(), data = new FormData(form);
    for (const key of Object.keys(labels) as (keyof Fields)[]) state.draft.fields[key] = String(data.get(key) ?? "");
    state.draft.type = String(data.get("type")); state.draft.note = String(data.get("note")); state.draft.confirmed = data.get("confirmed") === "on";
    state.dirty = JSON.stringify(state.draft) !== JSON.stringify(state.saved);
    syncButtons();
  };
  form.onsubmit = eventObject => {
    eventObject.preventDefault(); const state = current(); if (final(state)) return;
    const before = state.saved.fields.total;
    state.saved = structuredClone(state.draft); state.checks = validate(state.saved); state.dirty = false;
    state.status = state.checks.every(c => c.ok) ? "ready" : "review";
    event("Saved & revalidated", `Status: ${state.status}. Total: ${before || "not supplied"} -> ${state.saved.fields.total || "not supplied"}. ${state.saved.note || "No review note supplied."}`);
    announce(state.status === "ready" ? "Saved and revalidated: ready. Explicit approval is still required." : "Saved and revalidated: review. Resolve the failed checks before approval."); render();
  };
  document.querySelector<HTMLButtonElement>("#approve")!.onclick = () => {
    const state = current();
    if (final(state) || state.dirty || !validate(state.saved).every(c => c.ok)) { announce("Save changes and resolve failed checks before approval.", true); render(); return; }
    state.status = "approved"; event("Approved explicitly", "Saved sample fields now included in approved-only exports."); announce("Sample approved. Download JSON or CSV below to inspect the result."); render();
  };
  document.querySelector<HTMLButtonElement>("#reject")!.onclick = () => {
    const state = current(); if (final(state)) return;
    if (state.draft.note.trim().length < 3) { announce("Enter a rejection reason of at least 3 characters in the review note.", true); render("#review-note"); return; }
    state.rejectionReason = state.draft.note;
    state.draft = structuredClone(state.saved); state.dirty = false; state.status = "rejected";
    event("Rejected explicitly", `${state.rejectionReason}. Unsaved field/type edits were not saved.`);
    announce("Sample rejected and excluded from exports. Unsaved field/type edits were discarded; saved fields are shown. Reset to try again."); render();
  };
  document.querySelector<HTMLButtonElement>("#original-download")!.onclick = () => download(current().sample.filename, "text/plain;charset=utf-8", current().sample.original);
  document.querySelector<HTMLButtonElement>("#export-json")!.onclick = () => exportSamples("json");
  document.querySelector<HTMLButtonElement>("#export-csv")!.onclick = () => exportSamples("csv");
}
initialize();
render();
