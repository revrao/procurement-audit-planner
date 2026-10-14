// Workflow steps for one audit run. Each step resumes the run's named sandbox,
// does one bounded piece of work (well under a Hobby function's 300 s), and
// writes what happened to the run's durable stream, which the UI reads.
import { getWritable } from "workflow";
import { applyGate1, applyGate2, parseRisks, reviewVerdict } from "@/lib/gates";
import { redact } from "@/lib/redact";
import { createRunSandbox, readRepoFile, requireRepoFile, resumeRunSandbox, run, sandboxName, stopRunSandbox, unpackBundle, writeRepoFile } from "@/lib/run-sandbox";
import { REVALIDATION, type AgentStage, type Gate1Payload, type Gate2Payload, type GateRisk, type Mode, type NewEvent, type RunEvent, type StageKey } from "@/lib/run-types";
import { allDone, newTrack, runSlice, type Continuation, type SliceResult, type Track } from "@/lib/slice";
import { PYTHON, STAGE_DEFS, runsClaude, type Check } from "@/lib/stages";
import { repoDir } from "@/lib/spike";
import { DONE } from "@/lib/team-live";

type Emit = (e: NewEvent) => void;

/** Writes events in order and waits for them before the step returns. */
async function withEvents<T>(fn: (emit: Emit) => Promise<T>): Promise<T> {
  const writer = getWritable<RunEvent>().getWriter();
  let chain: Promise<void> = Promise.resolve();
  const emit: Emit = (e) => {
    const ev = redact({ t: Date.now(), ...e } as RunEvent);
    chain = chain.then(() => writer.write(ev)).catch(() => {});
  };
  try {
    return await fn(emit);
  } finally {
    await chain;
    writer.releaseLock();
  }
}

/** Runs Python from a string without shell quoting: piped in base64 to the venv Python. */
const pyCommand = (code: string) => `echo ${Buffer.from(code).toString("base64")} | base64 -d | ${PYTHON} -`;

const tail = (s: string, n = 3000) => (s.length > n ? `…${s.slice(-n)}` : s);

export async function announce(events: NewEvent[]) {
  "use step";
  await withEvents(async (emit) => events.forEach(emit));
}

export async function prepareRun(runId: string, mode: Mode) {
  "use step";
  await withEvents(async (emit) => {
    emit({ kind: "run", mode, sandbox: sandboxName(runId) });
    // Resume-or-create through the spike's openSandbox; the first run of a new
    // Part A bundle builds the snapshot (a few minutes).
    await createRunSandbox(runId, (e) => emit({ kind: "log", stage: "extract-rules", by: "host", text: `sandbox ${String(e.action)} ${String(e.sandboxId ?? "")}` }));
  });
}
prepareRun.maxRetries = 2;

export type StageStart = { claude: boolean; prompt: string; track: Track; blocked?: boolean };

export async function startStage(input: { runId: string; stage: AgentStage; mode: Mode; attempt: number; note?: string }): Promise<StageStart> {
  "use step";
  const def = STAGE_DEFS[input.stage];
  return withEvents(async (emit) => {
    const log = (text: string) => emit({ kind: "log", stage: input.stage, by: "host", text });
    emit({ kind: "stage", stage: input.stage, status: "running", attempt: input.attempt });
    const s = await resumeRunSandbox(input.runId);
    const repo = await repoDir(s);
    const track = newTrack(!!def.team);

    if (!runsClaude(input.stage, input.mode)) {
      if (def.seed === "seed-analysis.tar.gz") {
        const r = await unpackBundle(s, repo, def.seed);
        if (r.exitCode !== 0) throw new Error(`could not restore seed outputs: ${r.out}`);
      }
      log(`seeded run: restored the committed Part A outputs for this stage (${def.seed}); its checks still run on them below`);
      return { claude: false, prompt: "", track };
    }
    if (def.clear) {
      await run(s, def.clear, repo);
      log(`cleared previous outputs: ${def.clear}`);
    }
    if (def.precondition) {
      const r = await run(s, def.precondition.command, repo);
      const pass = r.exitCode === 0;
      emit({ kind: "check", stage: input.stage, name: `precondition: ${def.precondition.name}`, pass, command: def.precondition.command, output: tail(r.out) });
      if (!pass) return { claude: false, prompt: "", track, blocked: true };
    }
    log(`starting Claude Code (${def.team ? "agent team lead" : "main session"})`);
    return { claude: true, prompt: def.prompt(input.note), track };
  });
}
startStage.maxRetries = 2;

/** One slice of the stage's Claude Code turn; see lib/slice.ts. */
export async function claudeSlice(input: { runId: string; stage: AgentStage; prompt: string; cont?: Continuation; track: Track }): Promise<SliceResult> {
  "use step";
  return withEvents(async (emit) => {
    const s = await resumeRunSandbox(input.runId);
    return runSlice({ s, prompt: input.prompt, cont: input.cont, track: input.track, emit: (by, text) => emit({ kind: "log", stage: input.stage, by, text }) });
  });
}
// A retry reattaches from the same cursor: the bridge replays events, tools do not run twice.
claudeSlice.maxRetries = 2;

export type StageResult = { pass: boolean; risks?: GateRisk[]; verdict?: string | null };

export async function validateStage(input: { runId: string; stage: AgentStage; mode: Mode; track: Track; claude: boolean; blocked?: boolean; revalidation?: boolean }): Promise<StageResult> {
  "use step";
  const { stage, track } = input;
  const def = STAGE_DEFS[stage];
  return withEvents(async (emit) => {
    emit({ kind: "stage", stage, status: "validating", ...(input.revalidation ? { note: REVALIDATION } : {}) });
    const s = await resumeRunSandbox(input.runId);
    const repo = await repoDir(s);
    let pass = !input.blocked;
    const check = (name: string, ok: boolean, command: string, output: string) => {
      pass &&= ok;
      emit({ kind: "check", stage, name, pass: ok, command, output: tail(output) });
    };

    if (input.claude) {
      check("Claude Code turn ended normally, with no API or harness error", (track.endedBy === "stream-ended" || track.endedBy === "complete") && !track.error, "(harness)",
        `ended by: ${track.endedBy}; slices: ${track.slices}; tool calls: ${track.toolCalls} main, ${track.subagentToolCalls} sub-agent${track.error ? `; error: ${track.error}` : ""}`);
      for (const d of def.delegates ?? [])
        check(`delegated to the ${d} sub-agent`, track.delegatedTo.includes(d), "(tool-call log)", `Agent calls by subagent_type: ${track.delegatedTo.join(", ") || "none"}`);
      if (track.team) {
        const t = track.team;
        check("PLANNER DONE, CHALLENGER DONE and QA DONE reached the lead", allDone(t), "(teammate SendMessage calls)",
          Object.entries(DONE).map(([k, line]) => `${line}: ${t.done[k as keyof typeof DONE] ? `minute ${t.done[k as keyof typeof DONE]!.minute}` : "not received"}`).join("\n") +
          `\nteammates spawned: ${t.spawned.join(", ") || "none"}; keep-alive steers: ${t.steers} (${t.steerFailures} failed); lead turn ends: ${t.leadTurnEnds}`);
      }
    }
    if (!input.blocked) {
      for (const c of def.checks as Check[]) {
        const r = await run(s, c.command, repo);
        check(c.name, c.pass ? c.pass(r.exitCode, r.out) : r.exitCode === 0, c.command, `exit ${r.exitCode}\n${r.out}`);
      }
    }
    if (def.summary) {
      const r = await run(s, pyCommand(def.summary), repo);
      try {
        emit({ kind: "summary", stage, data: { ...(input.claude ? {} : { seeded: true }), ...JSON.parse(r.out) } });
      } catch {
        emit({ kind: "log", stage, by: "host", text: `summary unavailable: ${tail(r.out, 400)}` });
      }
    }
    let risks: GateRisk[] | undefined;
    let verdict: string | null | undefined;
    for (const f of def.files) {
      const content = await readRepoFile(s, repo, f).catch(() => null);
      if (content == null) continue;
      emit({ kind: "file", stage, path: f, content: content.length > 400_000 ? content.slice(0, 400_000) + "\n\n…(truncated)" : content });
      if (f.endsWith("auditor-comments.md")) risks = parseRisks(content);
      if (f.endsWith("review.md")) verdict = reviewVerdict(content);
    }
    if (stage === "risk-assessor") check("auditor-comments.md lists the risks for the gate", !!risks?.length, "(parse decision table)", `${risks?.length ?? 0} risk(s)`);
    emit({ kind: "stage", stage, status: pass ? "pass" : "fail" });
    await s.stop(); // state saved; the next step resumes it with a fresh session
    return { pass, risks, verdict };
  });
}
validateStage.maxRetries = 2;

// Gate 1 is checked with Part A's own parser (build_register.read_comments), so
// the revision stage reads exactly what the gate recorded.
const READ_COMMENTS = `import json, sys; sys.path.insert(0, '.claude/skills/risk-assessment'); import build_register as b; from pathlib import Path
d, g, p = b.read_comments(Path('outputs/auditor-comments.md')); print(json.dumps({'decisions': {k: v['decision'] for k, v in d.items()}, 'problems': p}))`;

export async function applyGate1Step(input: { runId: string; token: string; payload: Gate1Payload }): Promise<{ ok: boolean }> {
  "use step";
  return withEvents(async (emit) => {
    const s = await resumeRunSandbox(input.runId);
    const repo = await repoDir(s);
    const md = await requireRepoFile(s, repo, "outputs/auditor-comments.md");
    const { content, errors } = applyGate1(md, input.payload);
    if (errors.length) {
      emit({ kind: "gate-error", token: input.token, errors });
      return { ok: false };
    }
    await writeRepoFile(s, repo, "outputs/auditor-comments.md", content);
    const r = await run(s, pyCommand(READ_COMMENTS), repo);
    let ok = false;
    try {
      const parsed = JSON.parse(r.out) as { decisions: Record<string, string>; problems: string[] };
      const want = parseRisks(content).map((x) => x.id);
      ok = parsed.problems.length === 0 && want.length > 0 && want.every((id) => ["approve", "amend", "reject"].includes(parsed.decisions[id]));
    } catch {}
    emit({ kind: "check", stage: "gate1", name: "build_register.read_comments: every risk has a valid decision", pass: ok, command: "build_register.read_comments(outputs/auditor-comments.md)", output: tail(r.out) });
    emit({ kind: "file", stage: "gate1", path: "outputs/auditor-comments.md", content });
    if (!ok) {
      emit({ kind: "gate-error", token: input.token, errors: ["Part A's parser did not read the decisions back; see the gate 1 check"] });
      return { ok: false };
    }
    const counts = Object.values(input.payload.decisions).reduce<Record<string, number>>((m, d) => ((m[d.decision] = (m[d.decision] ?? 0) + 1), m), {});
    emit({ kind: "resolved", token: input.token, summary: `${input.payload.reviewer}, ${input.payload.date}: ${Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(", ")}` });
    emit({ kind: "stage", stage: "gate1", status: "done" });
    return { ok: true };
  });
}

export async function applyGate2Step(input: { runId: string; token: string; payload: Gate2Payload }): Promise<{ ok: boolean }> {
  "use step";
  return withEvents(async (emit) => {
    const s = await resumeRunSandbox(input.runId);
    const repo = await repoDir(s);
    const md = await requireRepoFile(s, repo, "outputs/review.md");
    const { content, errors } = applyGate2(md, input.payload);
    if (errors.length) {
      emit({ kind: "gate-error", token: input.token, errors });
      await s.stop();
      return { ok: false };
    }
    await writeRepoFile(s, repo, "outputs/review.md", content);
    const back = await requireRepoFile(s, repo, "outputs/review.md");
    const block = back.slice(back.search(/^## Auditor sign-off/m));
    const ok = new RegExp(`^Decision: ${input.payload.decision}$`, "m").test(block) && /^Reviewer: \S/m.test(block) && /^Date: \d{4}-\d{2}-\d{2}$/m.test(block);
    emit({ kind: "check", stage: "gate2", name: "review.md sign-off block recorded", pass: ok, command: "(re-read outputs/review.md)", output: block });
    emit({ kind: "file", stage: "gate2", path: "outputs/review.md", content: back });
    await s.stop();
    if (!ok) {
      emit({ kind: "gate-error", token: input.token, errors: ["The sign-off block did not read back as written"] });
      return { ok: false };
    }
    emit({ kind: "resolved", token: input.token, summary: `${input.payload.decision}: ${input.payload.reviewer}, ${input.payload.date}` });
    emit({ kind: "stage", stage: "gate2", status: "done" });
    return { ok: true };
  });
}

export async function finishRun(runId: string, status: "signed-off" | "aborted") {
  "use step";
  await withEvents(async (emit) => {
    await stopRunSandbox(runId).catch(() => {});
    emit({ kind: "end", status });
  });
  return { status };
}

export type { StageKey };
