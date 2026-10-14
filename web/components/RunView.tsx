"use client";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Markdown } from "@/components/Markdown";
import { REVALIDATION, STAGES, type Decision, type GateRisk, type Mode, type RunEvent, type StageKey, type StageStatus } from "@/lib/run-types";

type Ev<K extends RunEvent["kind"]> = Extract<RunEvent, { kind: K }>;
type StageView = { status?: StageStatus; attempt?: number; checks: Ev<"check">[]; summary?: Record<string, unknown> };
type View = {
  mode?: Mode;
  sandbox?: string;
  stages: Record<StageKey, StageView>;
  logs: Ev<"log">[];
  files: Record<string, Ev<"file">>;
  awaits: Ev<"await">[];
  resolved: Record<string, string>;
  gateErrors: Record<string, Ev<"gate-error">>;
  end?: Ev<"end">["status"];
};

const emptyView = (): View => ({
  stages: Object.fromEntries(STAGES.map((s) => [s.key, { checks: [] }])) as unknown as Record<StageKey, StageView>,
  logs: [],
  files: {},
  awaits: [],
  resolved: {},
  gateErrors: {},
});

function apply(prev: View, events: RunEvent[]): View {
  const v: View = { ...prev, stages: { ...prev.stages }, logs: [...prev.logs], files: { ...prev.files }, awaits: [...prev.awaits], resolved: { ...prev.resolved }, gateErrors: { ...prev.gateErrors } };
  for (const e of events) {
    switch (e.kind) {
      case "run":
        v.mode = e.mode;
        v.sandbox = e.sandbox;
        break;
      case "stage": {
        const s = v.stages[e.stage];
        const fresh = e.status === "running" && e.attempt !== undefined && e.attempt !== s.attempt;
        // A revalidation replaces the previous validation's checks; the stage-start precondition stays.
        const recheck = e.status === "validating" && e.note === REVALIDATION;
        const checks = fresh ? [] : recheck ? s.checks.filter((c) => c.name.startsWith("precondition: ")) : s.checks;
        v.stages[e.stage] = { ...s, status: e.status, attempt: e.attempt ?? s.attempt, checks, summary: fresh ? undefined : s.summary };
        break;
      }
      case "check":
        v.stages[e.stage] = { ...v.stages[e.stage], checks: [...v.stages[e.stage].checks, e] };
        break;
      case "summary":
        v.stages[e.stage] = { ...v.stages[e.stage], summary: e.data };
        break;
      case "log":
        v.logs.push(e);
        break;
      case "file":
        v.files[e.path] = e;
        break;
      case "await":
        v.awaits.push(e);
        break;
      case "resolved":
        v.resolved[e.token] = e.summary;
        break;
      case "gate-error":
        v.gateErrors[e.token] = e;
        break;
      case "end":
        v.end = e.status;
        break;
    }
  }
  if (v.logs.length > 3000) v.logs = v.logs.slice(-3000);
  return v;
}

const STATUS_LABEL: Record<StageStatus | "pending", string> = {
  pending: "Not started",
  running: "Running",
  validating: "Checking",
  pass: "PASS",
  fail: "FAIL",
  waiting: "Waiting for you",
  done: "Done",
};

const FILE_LABELS: [string, string][] = [
  ["outputs/review.md", "QA review & sign-off"],
  ["outputs/planning-memo.md", "Planning memo"],
  ["outputs/risk-control-matrix.md", "Risk-control matrix"],
  ["outputs/audit-program.md", "Audit program"],
  ["outputs/challenges.md", "Challenger log"],
  ["outputs/risk-register.md", "Risk register"],
  ["outputs/auditor-comments.md", "Auditor decisions (Gate 1)"],
];
const fileLabel = (p: string) => FILE_LABELS.find(([f]) => f === p)?.[1] ?? p;

const STAGE_CHECKS: Record<StageKey, string> = {
  "extract-rules": "Checked by verify_quotes.py: every rule quote is on its stated page of the rules PDF and every clause is covered.",
  analysis: "Checked by self_check.py (an independent re-derivation of one flagged item per test) and verify_history.py (every history item quoted from its page).",
  "risk-assessor": "Checked by rebuilding the register with build_register.py: every rating cites a rule, metric or history item; 0 errors, 0 warnings.",
  gate1: "Your decisions are written to auditor-comments.md and read back with Part A's own parser.",
  revision: "Checked by build_register.py (revision applied, 0 warnings) and build_pack.py --gate (every risk decided).",
  team: "Checked by run_checks.py (quotes, numbers, traceability, samples), the review.md verdict, and the three DONE messages reaching the lead.",
  gate2: "Your decision is written to the sign-off block of review.md and read back.",
};

const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

function verdictOf(md?: string) {
  const sec = md && /^## Verdict[ \t]*\n([\s\S]*?)(?=^## |(?![\s\S]))/m.exec(md)?.[1];
  return (sec && /READY FOR SIGN-OFF|BLOCKED/.exec(sec)?.[0]) || null;
}

function signoffOf(md?: string) {
  if (!md) return null;
  const at = md.search(/^## Auditor sign-off/m);
  if (at < 0) return null;
  const block = md.slice(at);
  const get = (k: string) => new RegExp(`^${k}:[ \\t]*(.*)$`, "m").exec(block)?.[1]?.trim() ?? "";
  const decision = get("Decision");
  if (!decision || decision.startsWith("<")) return null;
  return { decision, reviewer: get("Reviewer"), date: get("Date"), comments: get("Comments") };
}

export function RunView({ runId }: { runId: string }) {
  const [view, setView] = useState<View>(emptyView);
  const [status, setStatus] = useState<string>("loading");
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<StageKey | null>(null);
  const [tab, setTab] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    let next = 0;
    (async () => {
      while (!stop) {
        try {
          const res = await fetch(`/api/runs/${runId}/events?from=${next}`, { cache: "no-store" });
          if (res.status === 404) return setError("Run not found.");
          const body = (await res.json()) as { status: string; events: RunEvent[]; next: number };
          next = body.next;
          if (stop) return;
          if (body.events.length) setView((v) => apply(v, body.events));
          setStatus(body.status);
          setError("");
          if (["completed", "failed", "cancelled"].includes(body.status) && body.events.length === 0) return;
          await new Promise((r) => setTimeout(r, body.events.length ? 100 : 1500));
        } catch {
          setError("Connection lost; retrying…");
          await new Promise((r) => setTimeout(r, 4000));
        }
      }
    })();
    return () => {
      stop = true;
    };
  }, [runId]);

  const current = useMemo(() => {
    const active = STAGES.filter((s) => view.stages[s.key].status);
    return active.length ? active[active.length - 1].key : null;
  }, [view]);
  const shown = selected ?? current ?? "extract-rules";
  const pending = view.end ? undefined : [...view.awaits].reverse().find((a) => !view.resolved[a.token]);
  const fileKeys = FILE_LABELS.map(([f]) => f).filter((f) => view.files[f]);
  const activeTab = tab && view.files[tab] ? tab : fileKeys[0];

  async function cancel() {
    if (!confirm("Cancel this run? The agents stop; the sandbox's files are kept.")) return;
    await fetch(`/api/runs/${runId}/cancel`, { method: "POST" });
  }

  const finished = ["completed", "failed", "cancelled"].includes(status);
  return (
    <main>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <Link href="/" className="small">← All runs</Link>
          <h1>{view.mode === "seeded" ? "Seeded Demo Run" : view.mode === "full" ? "Full Run" : "Audit run"}</h1>
          <div className="small muted mono">{runId}</div>
        </div>
        <div className="row">
          <span className={`badge ${view.end === "signed-off" ? "pass" : view.end === "aborted" || status === "failed" || status === "cancelled" ? "fail" : pending ? "waiting" : "running"}`}>
            {view.end === "signed-off" ? "Signed off" : view.end === "aborted" ? "Ended" : status === "cancelled" ? "Cancelled" : status === "failed" ? "Failed" : pending ? "Waiting for you" : status === "loading" ? "Loading" : "Running"}
          </span>
          {!finished && <button className="danger" onClick={cancel}>Cancel run</button>}
        </div>
      </div>
      {error && <p className="error">{error}</p>}

      <FinalPanel view={view} />

      {pending && <ActionPanel key={pending.token} runId={runId} pending={pending} view={view} />}

      <div className="grid">
        <div>
          <div className="card">
            <h2>Stages</h2>
            <ul className="stages">
              {STAGES.map((s, i) => {
                const st = view.stages[s.key];
                const seeded = st.summary?.seeded === true;
                return (
                  <li key={s.key} className={shown === s.key ? "selected" : ""} onClick={() => setSelected(s.key)}>
                    <span className="small">{i + 1}. {s.label}{seeded && <span className="muted"> (seeded)</span>}{st.attempt && st.attempt > 1 ? <span className="muted"> · attempt {st.attempt}</span> : null}</span>
                    <span className={`badge ${st.status ?? "pending"}`}>{STATUS_LABEL[st.status ?? "pending"]}</span>
                  </li>
                );
              })}
            </ul>
          </div>
          <StageDetail stage={shown} view={view} />
        </div>
        <div>
          <div className="card">
            <h2>Outputs</h2>
            {fileKeys.length === 0 ? (
              <p className="small muted">The risk register, auditor decisions and the audit planning pack appear here as the stages produce them.</p>
            ) : (
              <>
                <div className="tabs">
                  {fileKeys.map((f) => (
                    <button key={f} className={f === activeTab ? "active" : ""} onClick={() => setTab(f)}>{fileLabel(f)}</button>
                  ))}
                </div>
                {activeTab && (
                  <>
                    <p className="small muted mono">{activeTab}</p>
                    <Markdown source={view.files[activeTab].content} />
                  </>
                )}
              </>
            )}
          </div>
          <Logs view={view} stage={selected} onAll={() => setSelected(null)} />
        </div>
      </div>
    </main>
  );
}

function FinalPanel({ view }: { view: View }) {
  const review = view.files["outputs/review.md"]?.content;
  const verdict = verdictOf(review);
  const signoff = signoffOf(review);
  const teamChecks = view.stages.team.checks;
  if (!verdict && view.stages.team.status !== "fail" && !view.end) return null;
  const runChecks = teamChecks.find((c) => c.name.startsWith("run_checks.py"));
  return (
    <div className="card">
      <h2>Result</h2>
      <div className="final">
        <div className={`box ${verdict === "READY FOR SIGN-OFF" ? "pass" : verdict ? "fail" : "waiting"}`}>
          <div className="small muted">Final QA verdict (run_checks.py, re-run by the app)</div>
          <div className="big">{verdict ?? "Not available"}</div>
          {runChecks && <div className="small">QA scripts in the sandbox: <b>{runChecks.pass ? "PASS" : "FAIL"}</b></div>}
        </div>
        <div className={`box ${signoff?.decision === "sign off" ? "pass" : signoff ? "fail" : "waiting"}`}>
          <div className="small muted">Auditor sign-off (Gate 2, recorded in review.md)</div>
          {signoff ? (
            <>
              <div className="big">{signoff.decision === "sign off" ? "Signed off" : "Returned to the team"}</div>
              <div className="small">{signoff.reviewer}, {signoff.date}{signoff.comments ? `: ${signoff.comments}` : ""}</div>
            </>
          ) : (
            <div className="big">{view.end === "aborted" ? "Not signed off" : "Awaiting the auditor"}</div>
          )}
        </div>
      </div>
    </div>
  );
}

function StageDetail({ stage, view }: { stage: StageKey; view: View }) {
  const st = view.stages[stage];
  const label = STAGES.find((s) => s.key === stage)!.label;
  return (
    <div className="card">
      <h2>{label}</h2>
      <p className="small muted">{STAGE_CHECKS[stage]}</p>
      {st.summary && <Summary data={st.summary} />}
      {st.checks.length === 0 ? (
        <p className="small muted">No checks yet.</p>
      ) : (
        st.checks.map((c, i) => (
          <details key={i} className="check">
            <summary>
              <span className={`badge ${c.pass ? "pass" : "fail"}`}>{c.pass ? "PASS" : "FAIL"}</span>
              <span className="small">{c.name}</span>
            </summary>
            <div className="small muted mono">$ {c.command}</div>
            <pre>{c.output}</pre>
          </details>
        ))
      )}
    </div>
  );
}

const pretty = (k: string) => k.replace(/_/g, " ");
function Summary({ data }: { data: Record<string, unknown> }) {
  const rows: [string, string][] = [];
  const walk = (prefix: string, v: unknown) => {
    if (v && typeof v === "object" && !Array.isArray(v)) for (const [k, x] of Object.entries(v)) walk(prefix ? `${prefix} › ${pretty(k)}` : pretty(k), x);
    else rows.push([prefix, typeof v === "number" ? (prefix.includes("gbp") ? `£${v.toLocaleString("en-GB", { minimumFractionDigits: 2 })}` : v.toLocaleString("en-GB")) : String(v)]);
  };
  walk("", data);
  return (
    <>
      <h3>Key figures (computed by Python in the sandbox)</h3>
      <dl className="kv">
        {rows.map(([k, v]) => (
          <div key={k} style={{ display: "contents" }}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

function Logs({ view, stage, onAll }: { view: View; stage: StageKey | null; onAll: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const logs = (stage ? view.logs.filter((l) => l.stage === stage) : view.logs).slice(-600);
  useEffect(() => {
    const el = ref.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 80) el.scrollTop = el.scrollHeight;
  }, [logs.length]);
  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Activity log{stage ? `: ${STAGES.find((s) => s.key === stage)!.label}` : ""}</h2>
        {stage && <button className="secondary" onClick={onAll}>Show all stages</button>}
      </div>
      <p className="small muted">Tool calls by the main session or lead, sub-agents and teammates, and the harness (host). Inputs are shortened.</p>
      <div className="logs" ref={ref}>
        {logs.length === 0 ? <div className="by">Nothing yet.</div> : logs.map((l, i) => (
          <div key={i}>
            <span className="by">{new Date(l.t).toLocaleTimeString()} </span>
            <span className={`by-${l.by}`}>[{l.by}]</span> {l.text}
          </div>
        ))}
      </div>
    </div>
  );
}

async function resume(runId: string, token: string, payload: unknown) {
  const res = await fetch(`/api/runs/${runId}/resume`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token, payload }) });
  if (!res.ok) throw new Error(((await res.json().catch(() => ({}))) as { error?: string }).error ?? `HTTP ${res.status}`);
}

function ActionPanel({ runId, pending, view }: { runId: string; pending: Ev<"await">; view: View }) {
  const [sentAt, setSentAt] = useState(0);
  const [error, setError] = useState("");
  const gateError = view.gateErrors[pending.token];
  const errors = gateError && gateError.t > sentAt - 5000 ? gateError.errors : [];
  const waitingForRun = sentAt > 0 && !(gateError && gateError.t > sentAt - 5000);

  async function send(payload: unknown) {
    setError("");
    try {
      setSentAt(Date.now());
      await resume(runId, pending.token, payload);
    } catch (e) {
      setSentAt(0);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const footer = (
    <>
      {errors.map((e) => <p key={e} className="error">{e}</p>)}
      {error && <p className="error">{error}</p>}
      {waitingForRun && <p className="small muted">Submitted; the run is recording it in the sandbox…</p>}
    </>
  );

  if (pending.type === "retry")
    return (
      <div className="card" style={{ borderColor: "var(--fail)" }}>
        <h2>{STAGES.find((s) => s.key === pending.stage)!.label} failed its checks</h2>
        <p className="small">Open the stage on the left to see which check failed and its output. Revalidating re-runs only the checks on the stage's saved outputs (no agent runs, nothing is cleared). Retrying re-runs the stage from its start in the same sandbox.</p>
        <div className="row">
          <button onClick={() => send({ action: "revalidate" })} disabled={waitingForRun}>Revalidate</button>
          <button onClick={() => send({ action: "retry" })} disabled={waitingForRun}>Retry stage</button>
          <button className="danger" onClick={() => send({ action: "abort" })} disabled={waitingForRun}>End run</button>
        </div>
        {footer}
      </div>
    );
  if (pending.type === "gate1") return <Gate1Form risks={pending.risks ?? []} onSubmit={send} busy={waitingForRun} footer={footer} />;
  return <Gate2Form verdict={pending.verdict} onSubmit={send} busy={waitingForRun} footer={footer} />;
}

function Gate1Form({ risks, onSubmit, busy, footer }: { risks: GateRisk[]; onSubmit: (p: unknown) => void; busy: boolean; footer: React.ReactNode }) {
  const [decisions, setDecisions] = useState<Record<string, { decision: Decision | ""; comment: string }>>(() => Object.fromEntries(risks.map((r) => [r.id, { decision: "", comment: "" }])));
  const [reviewer, setReviewer] = useState("");
  const [date, setDate] = useState(today);
  const [general, setGeneral] = useState("");
  const set = (id: string, k: "decision" | "comment", v: string) => setDecisions((d) => ({ ...d, [id]: { ...d[id], [k]: v } }));
  return (
    <div className="card" style={{ borderColor: "var(--wait)" }}>
      <h2>Gate 1: your decision on each risk</h2>
      <p className="small">
        Read the <b>Risk register</b> under Outputs, then decide each risk. <b>Approve</b> keeps it in scope as rated. <b>Amend</b> keeps it with
        the change you describe. <b>Reject</b> removes it from the audit scope (say why). The risk assessor then applies your decisions as a revision.
      </p>
      <table className="form">
        <thead>
          <tr><th>Risk</th><th>L × I = score</th><th>Decision</th><th style={{ width: "34%" }}>Comment</th></tr>
        </thead>
        <tbody>
          {risks.map((r) => (
            <tr key={r.id}>
              <td><b>{r.id}</b> {r.risk}</td>
              <td className="mono">{r.likelihood} × {r.impact} = {r.score}<div className="small muted">{r.band}</div></td>
              <td>
                <select value={decisions[r.id]?.decision ?? ""} onChange={(e) => set(r.id, "decision", e.target.value)}>
                  <option value="">choose…</option>
                  <option value="approve">approve</option>
                  <option value="amend">amend</option>
                  <option value="reject">reject</option>
                </select>
              </td>
              <td><input value={decisions[r.id]?.comment ?? ""} onChange={(e) => set(r.id, "comment", e.target.value)} placeholder={decisions[r.id]?.decision && decisions[r.id].decision !== "approve" ? "required" : "optional"} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row" style={{ marginTop: 12, alignItems: "flex-end" }}>
        <label>Reviewer<input value={reviewer} onChange={(e) => setReviewer(e.target.value)} /></label>
        <label>Date<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <label style={{ flex: 1, minWidth: 240 }}>General comments (optional)<input value={general} onChange={(e) => setGeneral(e.target.value)} /></label>
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <button disabled={busy} onClick={() => onSubmit({ reviewer, date, general, decisions })}>Record decisions</button>
        <button className="secondary" disabled={busy} onClick={() => setDecisions((d) => Object.fromEntries(Object.entries(d).map(([k, v]) => [k, { ...v, decision: "approve" }])))}>Approve all</button>
      </div>
      {footer}
    </div>
  );
}

function Gate2Form({ verdict, onSubmit, busy, footer }: { verdict?: string; onSubmit: (p: unknown) => void; busy: boolean; footer: React.ReactNode }) {
  const ready = verdict === "READY FOR SIGN-OFF";
  const [decision, setDecision] = useState<"sign off" | "return to the team">(ready ? "sign off" : "return to the team");
  const [reviewer, setReviewer] = useState("");
  const [date, setDate] = useState(today);
  const [comments, setComments] = useState("");
  return (
    <div className="card" style={{ borderColor: "var(--wait)" }}>
      <h2>Gate 2: auditor sign-off</h2>
      <p className="small">
        QA verdict: <span className={`badge ${ready ? "pass" : "fail"}`}>{verdict ?? "unknown"}</span>. Review the <b>Planning memo</b>, <b>Audit program</b>,
        <b> Challenger log</b> and <b>QA review</b> under Outputs. Sign off only on a READY FOR SIGN-OFF review; returning the pack re-runs the agent team with your comments.
      </p>
      <div className="row">
        <label className="row" style={{ flexDirection: "row" }}><input type="radio" checked={decision === "sign off"} disabled={!ready} onChange={() => setDecision("sign off")} /> Sign off</label>
        <label className="row" style={{ flexDirection: "row" }}><input type="radio" checked={decision === "return to the team"} onChange={() => setDecision("return to the team")} /> Return to the team</label>
      </div>
      <div className="row" style={{ marginTop: 12, alignItems: "flex-end" }}>
        <label>Reviewer<input value={reviewer} onChange={(e) => setReviewer(e.target.value)} /></label>
        <label>Date<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <label style={{ flex: 1, minWidth: 240 }}>Comments{decision === "return to the team" ? " (required)" : " (optional)"}<input value={comments} onChange={(e) => setComments(e.target.value)} /></label>
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <button disabled={busy} onClick={() => onSubmit({ decision, reviewer, date, comments })}>{decision === "sign off" ? "Sign off the pack" : "Return to the team"}</button>
      </div>
      {footer}
    </div>
  );
}
