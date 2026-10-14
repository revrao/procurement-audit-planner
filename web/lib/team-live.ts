// Live agent-team probe: the real planner, challenger and qa-reviewer, unchanged,
// run by the lead as CLAUDE.md "How the lead runs the team" steps 1-4 describe.
//
// The Claude Code bridge ends a turn's query (and the in-process teammates with
// it) at the first result once no host user message is still active. This probe
// tests whether steering the running turn (HarnessAgent.experimental_steer, the
// bridge's mid-turn user-message channel) keeps the lead's turn open until
// PLANNER DONE, CHALLENGER DONE and QA DONE have all reached the lead.
import { readFile } from "node:fs/promises";
import path from "node:path";
import { getAgent, repoDir, sh, type Log, type SandboxSession } from "@/lib/spike";

export const TEAMMATES = ["planner", "challenger", "qa-reviewer"];
export const DONE = { planner: "PLANNER DONE", challenger: "CHALLENGER DONE", qa: "QA DONE" } as const;
export type DoneKey = keyof typeof DONE;

// Outputs the team itself produces; removed so the run must recreate them.
export const TEAM_OUTPUTS = ["outputs/audit-plan.json", "outputs/planning-memo.md", "outputs/risk-control-matrix.md",
  "outputs/audit-program.md", "outputs/samples", "outputs/pack-figures.json", "outputs/challenges.md", "outputs/review.md"];

export const LEAD_PROMPT = `You are the lead (the main session). The auditor gate has been completed.
Run the Phase 3 agent team exactly as CLAUDE.md "How the lead (the main session) runs the team" steps 1-4 describe:
gate check, spawn planner, challenger and qa-reviewer as named teammates from .claude/agents/, let the team run itself,
wait until PLANNER DONE, CHALLENGER DONE and QA DONE have all arrived, then shut the three teammates down.
Do none of their work yourself.
Messages starting with [host] are keep-alive pings from the automated harness, not from the auditor. While any of the
three DONE lines is still missing, answer each ping by waiting about 30 seconds with one Bash command
(\`sleep 30\`; if that is refused, \`python3 -c "import time; time.sleep(30)"\`) and then keep waiting the same way.
Do not end your turn while the team is still working.
After the shutdown, give the step 5 report, then end with exactly one line:
TEAM_RUN: COMPLETE <the QA verdict> received=<each DONE line you received, verbatim, separated by " | ">`;

export const KEEPALIVE = "[host] keep-alive: wait about 30 seconds again unless PLANNER DONE, CHALLENGER DONE and QA DONE have all arrived.";
// Shorter than the lead's 30 s wait, so a fresh ping is always queued before the lead could end its turn.
export const KEEPALIVE_EVERY_MS = 20_000;
export const MAX_KEEPALIVES = 300;

export type TeamLiveResult = { pass: boolean; [k: string]: unknown };

export async function runTeamLive(s: SandboxSession, log: Log, deadlineMs: number): Promise<TeamLiveResult> {
  // 1. Post-gate inputs in, team outputs out; the gate must pass before the lead starts.
  const repo = await repoDir(s);
  const tarball = await readFile(path.join(process.cwd(), ".bundle/team-inputs.tar.gz"));
  await (s as any).writeBinaryFile({ path: `${repo}/team-inputs.tar.gz`, content: tarball });
  const prep = await sh(s, `tar -xzf team-inputs.tar.gz && rm team-inputs.tar.gz && rm -rf ${TEAM_OUTPUTS.join(" ")} && .venv/bin/python .claude/skills/audit-program/build_pack.py --gate`);
  log({ step: "prep", ...prep });
  if (prep.exitCode !== 0) return { pass: false, error: "gate failed in sandbox before the team started", prep: prep.out };

  // 2. One lead turn, kept open by host steering.
  const a = await getAgent();
  const session = await a.createSession({ sandboxSession: s });
  const ac = new AbortController();
  const t0 = Date.now();
  const at = () => +((Date.now() - t0) / 60000).toFixed(2);
  const deadline = setTimeout(() => ac.abort(new Error("deadline")), deadlineMs);

  const done: Partial<Record<DoneKey, { minute: number; to: string; message: string }>> = {};
  const steers: { minute: number; kind: string; ok: boolean; error?: string }[] = [];
  let leadText = "";
  let finishSteps = 0;
  let lastSteer = 0;
  let finalSent = false;
  let endedBy = "stream-ended";
  let streamError: string | undefined;
  const spawned = new Set<string>();
  let started = false;
  const ticker = setInterval(() => {
    if (started && !finalSent && !allDone() && steers.length < MAX_KEEPALIVES && Date.now() - lastSteer >= KEEPALIVE_EVERY_MS)
      void steer("keepalive", KEEPALIVE);
  }, 2_000);

  const steer = async (kind: string, text: string) => {
    lastSteer = Date.now();
    try {
      await a.experimental_steer({ session, text });
      steers.push({ minute: at(), kind, ok: true });
      log({ step: "steer", kind, ok: true, minute: at() });
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      steers.push({ minute: at(), kind, ok: false, error });
      log({ step: "steer", kind, ok: false, error, minute: at() });
    }
  };
  const allDone = () => (Object.keys(DONE) as DoneKey[]).every((k) => done[k]);

  try {
    const result = await a.stream({ session, prompt: LEAD_PROMPT, abortSignal: ac.signal });
    for await (const part of result.stream as AsyncIterable<any>) {
      if (part.type === "text-delta") leadText += part.text;
      else if (part.type === "tool-call") {
        const input = typeof part.input === "string" ? part.input : JSON.stringify(part.input ?? {});
        log({ step: "tool", by: "lead", tool: part.toolName, input: input.slice(0, 300), minute: at() });
        const name = /"name"\s*:\s*"([^"]+)"/.exec(input)?.[1];
        if (/agent|task/i.test(part.toolName) && name) spawned.add(name);
        started = true; // pings start once the lead is working
      } else if (part.type === "raw" && part.rawValue?.parent_tool_use_id && part.rawValue?.type === "assistant") {
        for (const b of part.rawValue.message?.content ?? []) {
          if (b?.type !== "tool_use") continue;
          const input = JSON.stringify(b.input ?? {});
          log({ step: "tool", by: "teammate", tool: b.name, input: input.slice(0, 300), minute: at() });
          if (!/SendMessage/i.test(b.name)) continue;
          const to = String(b.input?.to ?? b.input?.recipient ?? "");
          if (TEAMMATES.includes(to)) continue; // only DONE lines addressed to the lead count
          for (const k of Object.keys(DONE) as DoneKey[]) {
            if (!done[k] && input.includes(DONE[k])) {
              done[k] = { minute: at(), to, message: String(b.input?.message ?? b.input?.content ?? "").slice(0, 200) };
              log({ step: "done", key: k, ...done[k] });
            }
          }
        }
      } else if (part.type === "raw" && part.rawValue?.type === "system") {
        log({ step: "system", subtype: part.rawValue.subtype, minute: at() });
      } else if (part.type === "finish-step") {
        finishSteps++;
        log({ step: "lead-turn-end", n: finishSteps, minute: at(), tail: leadText.slice(-200) });
        if (allDone() && !finalSent) {
          finalSent = true;
          void steer("final", "[host] All three DONE lines were sent to you. Finish steps 4 and 5 and end with the TEAM_RUN line.");
        } else if (!allDone() && !finalSent) {
          void steer("after-turn-end", KEEPALIVE); // best effort: loses if the bridge already closed the query
        } else if (finalSent && /TEAM_RUN:/.test(leadText)) {
          endedBy = "complete";
          ac.abort(new Error("complete"));
        }
      } else if (part.type === "error") {
        streamError = String(part.error?.message ?? part.error);
        log({ step: "claude-error", error: streamError, minute: at() });
      }
    }
  } catch (e) {
    const reason = ac.signal.reason instanceof Error ? ac.signal.reason.message : undefined;
    if (reason === "deadline") endedBy = "deadline";
    else if (reason !== "complete") streamError = e instanceof Error ? e.message : String(e);
  } finally {
    clearTimeout(deadline);
    clearInterval(ticker);
    await session.detach().catch(() => {});
  }

  const minutes = at();
  const review = await sh(s, `grep -m1 -oE "READY FOR SIGN-OFF|BLOCKED" outputs/review.md`);
  const files = await sh(s, `ls ${TEAM_OUTPUTS.join(" ")} 2>&1 | head -30`);
  const leadReceived = /TEAM_RUN:\s*COMPLETE/.test(leadText);
  const turnClosedEarly = !allDone() && endedBy === "stream-ended";
  return {
    pass: allDone() && leadReceived && review.exitCode === 0 && endedBy !== "deadline" && !streamError,
    minutes,
    endedBy,
    streamError,
    teammatesSpawned: [...spawned],
    doneToLead: done,
    leadConfirmedReceipt: leadReceived,
    reviewVerdict: review.exitCode === 0 ? review.out : null,
    steers,
    leadTurnEnds: finishSteps,
    turnClosedBeforeAllDone: turnClosedEarly,
    teamOutputs: files.out,
    leadReplyTail: leadText.trim().slice(-1500),
  };
}
