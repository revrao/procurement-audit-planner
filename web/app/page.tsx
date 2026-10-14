"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { DEV_ONLY, STAGES, type Mode } from "@/lib/run-types";

type Recent = { runId: string; mode: Mode; startedAt: string };
const KEY = "audit-runs";

function loadRecent(): Recent[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]") as Recent[];
  } catch {
    return [];
  }
}

const STAGE_HELP: Record<string, string> = {
  "extract-rules": "Turns the council's Contract Procedure Rules PDF into testable rules, each with a verbatim quote. Checked by verify_quotes.py against the PDF.",
  analysis: "Two sub-agents in parallel: the spend analyst writes and runs Python over every payment (threshold clustering, split purchases, duplicates, off-contract…); the findings analyst records past audit history and the council's risk scoring method. Checked by self_check.py and verify_history.py.",
  "risk-assessor": "Rates each risk on the council's 5×5 likelihood × impact matrix; every rating must cite a rule, a metric or a history item. Checked by rebuilding the register with build_register.py (0 errors, 0 warnings).",
  gate1: "You, as the auditor, approve, amend or reject each risk.",
  revision: "The risk assessor applies your decisions as a register revision. Checked by build_register.py and the auditor-gate check (build_pack.py --gate).",
  team: "An agent team: the planner builds the audit pack, the challenger challenges it, the QA reviewer runs the four QA scripts and writes the verdict. Checked by run_checks.py (quotes, numbers, traceability, samples).",
  gate2: "You sign off the pack (only on a READY FOR SIGN-OFF verdict) or return it to the team.",
};

export default function Home() {
  const router = useRouter();
  const [recent, setRecent] = useState<Recent[]>([]);
  const [busy, setBusy] = useState<Mode | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => setRecent(loadRecent()), []);

  async function newRun(mode: Mode) {
    setBusy(mode);
    setError("");
    setNotice("");
    const res = await fetch("/api/runs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ mode }) });
    const body = (await res.json().catch(() => ({}))) as { runId?: string; error?: string };
    if (!res.ok || !body.runId) {
      setBusy(null);
      // 409: another demo run is active on this deployment; not an error on the visitor's side.
      if (res.status === 409) return setNotice(body.error ?? "A demo run is already in progress. Please try again later.");
      return setError(body.error ?? `Could not start a run (HTTP ${res.status}).`);
    }
    try {
      localStorage.setItem(KEY, JSON.stringify([{ runId: body.runId, mode, startedAt: new Date().toISOString() }, ...loadRecent()].slice(0, 20)));
    } catch {}
    router.push(`/runs/${body.runId}`);
  }

  return (
    <main>
      <h1>Procurement Audit Planner</h1>
      <p className="muted" style={{ maxWidth: 820 }}>
        An AI agent system that plans an internal audit of procurement at West Berkshire Council from public data. Agents read the
        council&apos;s purchasing rules, analyse every payment, rate the risks and draft the audit plan; Python computes every number;
        a human auditor approves at two gates. Results are <i>risk indicators to investigate</i>, never findings of wrongdoing.
      </p>

      <div className="card">
        <h2>Start a run</h2>
        <div className="choices">
          <div className="choice recommended">
            <div className="row"><b>Seeded Demo Run</b><span className="badge pass">Recommended for review</span></div>
            <p className="small">
              Starts from the rules, spend analytics and audit history already produced in Part A (their validators still re-run in the
              sandbox and must PASS), then runs <b>live</b>: the risk assessor, <b>Gate 1</b>, the register revision, the
              planner / challenger / QA agent team and <b>Gate 2</b>. About 25–35 minutes of agent time.
            </p>
            <button onClick={() => newRun("seeded")} disabled={!!busy}>{busy === "seeded" ? "Starting…" : "New Seeded Demo Run"}</button>
          </div>
          {DEV_ONLY && (
          <div className="choice">
            <div className="row"><b>Full Run</b><span className="badge waiting">Local dev only</span></div>
            <p className="small">
              Every stage runs live, including rule extraction from the PDF and the two analysis agents over ~10,600 payments. Roughly an
              hour of agent time and noticeably more API usage.
            </p>
            <button className="secondary" onClick={() => newRun("full")} disabled={!!busy}>{busy === "full" ? "Starting…" : "New Full Run"}</button>
          </div>
          )}
        </div>
        {notice && <p className="small" style={{ color: "var(--wait)" }}>{notice}</p>}
        {error && <p className="error">{error}</p>}
        <p className="small muted">
          You can leave the page at any time: the run continues in the background and its page picks up where it is. The run waits
          for you at each gate.
        </p>
      </div>

      <div className="card">
        <h2>The workflow</h2>
        <ol className="flow">
          {STAGES.map((s) => (
            <li key={s.key}>
              <b>{s.label}</b> {s.kind === "gate" && <span className="badge waiting">human</span>}
              <div className="small muted">{STAGE_HELP[s.key]}</div>
            </li>
          ))}
        </ol>
        <p className="small muted">
          Every agent stage ends with deterministic checks from Part A run inside the sandbox. A stage shows <span className="badge pass">PASS</span> only
          when those checks pass, never because an agent says it succeeded. A <span className="badge fail">FAIL</span> stage can be retried.
        </p>
      </div>

      <div className="card">
        <h2>Runs started in this browser</h2>
        {recent.length === 0 ? (
          <p className="muted small">None yet.</p>
        ) : (
          <ul>
            {recent.map((r) => (
              <li key={r.runId}>
                <Link href={`/runs/${r.runId}`}>{r.mode === "seeded" ? "Seeded demo" : "Full"} run, {new Date(r.startedAt).toLocaleString()}</Link>{" "}
                <span className="muted small mono">{r.runId}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <About />
    </main>
  );
}

function About() {
  return (
    <div className="card">
      <h2>About: how it is built</h2>
      <div className="about">
        <div>
          <h3>Skills</h3>
          <ul className="small">
            <li><b>extract-rules</b>: rules PDF → rules.json with verbatim quotes</li>
            <li><b>risk-assessment</b>: the rating method; build_register.py renders the register</li>
            <li><b>audit-program</b>: the planning method; build_pack.py draws samples and renders the pack</li>
          </ul>
        </div>
        <div>
          <h3>Agents</h3>
          <ul className="small">
            <li><b>spend-analyst</b> and <b>findings-analyst</b> (sub-agents)</li>
            <li><b>risk-assessor</b> (sub-agent)</li>
            <li><b>planner</b>, <b>challenger</b>, <b>qa-reviewer</b> (agent team, coordinating by message)</li>
          </ul>
        </div>
        <div>
          <h3>Runtime</h3>
          <ul className="small">
            <li>Claude Code runs the unchanged Part A repository inside one persistent Vercel Sandbox per run (AI SDK harness).</li>
            <li>A durable Vercel Workflow drives the stages in short steps and pauses at the gates, so no request has to stay open.</li>
            <li>API keys stay on the server; the browser only sees run events.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
