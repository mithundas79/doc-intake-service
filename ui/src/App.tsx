import { useCallback, useEffect, useState } from "react";

/*
 * Thin client over the FastAPI service. All judgment lives server-side;
 * this page uploads a document and renders what came back - the extracted
 * record, the trained classifier's confidence, the rule results and the
 * verdict - plus the model's own honesty note from /api/health.
 */

interface RuleResult {
  ok: boolean;
  rule: string;
  detail: string | null;
}

interface Processed {
  name: string;
  sha256: string;
  ocr_used: boolean;
  ocr_confidence: number | null;
  record: Record<string, unknown>;
  prediction: { label: string; confidence: number; alternatives: [string, number][] };
  checks: RuleResult[];
  verdict: "file" | "review";
}

export function App(): JSX.Element {
  const [health, setHealth] = useState<{ model_present: boolean; model_note: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Processed | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setError("The API is not reachable - is the server running on :8000?"));
  }, []);

  const upload = useCallback(async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await fetch("/api/documents", { method: "POST", body: form });
      if (!r.ok) {
        const body = (await r.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? `upload failed (${r.status})`);
      }
      setResult((await r.json()) as Processed);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const fails = result?.checks.filter((c) => !c.ok) ?? [];
  const pct = (n: number): string => `${Math.round(n * 100)}%`;

  return (
    <div className="wrap">
      <style>{CSS}</style>
      <header>
        <h1>doc-intake-service</h1>
        <p className="lede">
          Upload a scanned document (or a .txt to skip OCR). The Python backend reads it with
          native Tesseract, a <b>trained classifier</b> names the document type with a confidence,
          and deterministic rules decide whether it files itself or waits for a person.{" "}
          <a href="https://github.com/mithundas79/doc-intake-service">Source on GitHub</a>.
        </p>
        {health && <p className="banner">{health.model_note}</p>}
        {error && <p className="banner err">{error}</p>}
      </header>

      <div className="bar">
        <label className="file">
          {busy ? "Working…" : "Choose a document"}
          <input
            type="file"
            accept="image/*,.txt"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void upload(f);
              e.target.value = "";
            }}
          />
        </label>
        <span className="muted">PNG, JPG or TXT · processed locally by your own server</span>
      </div>

      {result && (
        <div className="cols">
          <div>
            <div className="card">
              <h2>Classifier</h2>
              <div className="predrow">
                <b>{result.prediction.label}</b>
                <div className="meter">
                  <i style={{ width: pct(result.prediction.confidence) }} />
                </div>
                <span>{pct(result.prediction.confidence)}</span>
              </div>
              <p className="muted">
                next:{" "}
                {result.prediction.alternatives
                  .map(([l, c]) => `${l} ${pct(c)}`)
                  .join(" · ")}
                {result.ocr_used
                  ? ` — OCR confidence ${result.ocr_confidence ?? "?"}%`
                  : " — text upload, OCR skipped"}
              </p>
            </div>
            <div className="card">
              <h2>Extracted record</h2>
              <pre>{JSON.stringify(result.record, null, 2)}</pre>
              <p className="muted">sha256 {result.sha256.slice(0, 16)}…</p>
            </div>
          </div>
          <div>
            <div className="card">
              <h2>Rule checks</h2>
              {result.checks.map((c, i) => (
                <div key={i} className="rule">
                  <span className={c.ok ? "pill ok" : "pill bad"}>{c.ok ? "pass" : "check"}</span>
                  <div>
                    <b>{c.rule}</b>
                    <div className="muted">{c.detail}</div>
                  </div>
                </div>
              ))}
            </div>
            <div className="card">
              <h2>Verdict</h2>
              {result.verdict === "file" ? (
                <p>
                  <span className="pill ok">files itself</span>{" "}
                  <span className="muted">Every rule passed.</span>
                </p>
              ) : (
                <p>
                  <span className="pill bad">held for review</span>{" "}
                  <span className="muted">
                    {fails.length} rule{fails.length > 1 ? "s" : ""} failed — a person looks at this
                    one. That is the correct outcome, not a failure.
                  </span>
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      <footer className="muted">
        Demo system: the classifier is trained on a synthetic corpus and will not handle every real
        document — see the README for what production hardening requires. MIT licensed.
      </footer>
    </div>
  );
}

const CSS = `
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #f6f8fa; color: #0f172a;
         font: 15px/1.5 "Segoe UI", system-ui, sans-serif; }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 28px 20px 40px; }
  h1 { margin: 0; font-size: 28px; }
  .lede { color: #475569; max-width: 75ch; }
  a { color: #0891b2; }
  .banner { background: #fff7ed; border: 1.5px solid #fdba74; color: #9a3412;
            border-radius: 8px; padding: 8px 12px; font-size: 13px; max-width: 75ch; }
  .banner.err { background: #fef2f2; border-color: #fca5a5; color: #b91c1c; }
  .bar { display: flex; gap: 12px; align-items: center; margin: 14px 0 18px; flex-wrap: wrap; }
  .file { border: 1.5px solid #cbd5e1; background: #fff; border-radius: 8px;
          padding: 8px 14px; cursor: pointer; }
  .file input { display: none; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 900px) { .cols { grid-template-columns: 1fr; } }
  .card { background: #fff; border: 1.5px solid #e2e8f0; border-radius: 10px;
          padding: 14px 16px; margin-bottom: 16px; }
  .card h2 { margin: 0 0 10px; font-size: 15px; }
  pre { margin: 0; font-size: 12.5px; overflow-x: auto; }
  .rule { display: flex; gap: 10px; padding: 8px 0; border-top: 1px solid #eef2f6; font-size: 13.5px; }
  .pill { display: inline-block; border-radius: 999px; padding: 2px 10px; font-size: 12px; font-weight: 600; }
  .pill.ok { background: #ecfdf5; color: #0f766e; }
  .pill.bad { background: #fff7ed; color: #b45309; }
  .muted { color: #64748b; font-size: 13px; }
  .predrow { display: flex; align-items: center; gap: 12px; font-size: 16px; }
  .meter { flex: 1; height: 8px; background: #eef2f6; border-radius: 4px; overflow: hidden; }
  .meter i { display: block; height: 100%; background: #0891b2; }
  footer { margin-top: 8px; }
`;
