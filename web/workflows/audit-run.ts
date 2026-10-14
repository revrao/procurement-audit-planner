// One durable workflow per audit run: the full Part A flow, stage by stage,
// pausing at the two human gates. The workflow only orchestrates; every piece
// of work is a step in ./steps.ts. A stage that fails its checks waits for the
// auditor to retry it or end the run.
import { createHook, getWorkflowMetadata } from "workflow";
import { MAX_SLICES, tokenFor, type AgentStage, type Gate1Payload, type Gate2Payload, type GateRisk, type Mode, type RetryPayload } from "@/lib/run-types";
import { announce, applyGate1Step, applyGate2Step, claudeSlice, finishRun, prepareRun, startStage, validateStage, type StageResult } from "./steps";

export async function auditRun(input: { mode: Mode }) {
  "use workflow";
  const { workflowRunId: runId } = getWorkflowMetadata();
  const mode = input.mode;
  let seq = 0; // makes every retry hook token unique within the run

  async function runStage(stage: AgentStage, note?: string): Promise<StageResult | null> {
    for (let attempt = 1; ; attempt++) {
      const start = await startStage({ runId, stage, mode, attempt, note });
      let track = start.track;
      if (start.claude) {
        let r = await claudeSlice({ runId, stage, prompt: start.prompt, track });
        for (let i = 1; !r.done && i < MAX_SLICES; i++) r = await claudeSlice({ runId, stage, prompt: "", cont: r.cont, track: r.track });
        track = r.track;
      }
      // "revalidate" re-runs only the checks on the stage's saved outputs, with the
      // same Claude track: nothing is cleared and no agent runs.
      for (let revalidation = false; ; revalidation = true) {
        const v = await validateStage({ runId, stage, mode, track, claude: start.claude, blocked: start.blocked, ...(revalidation ? { revalidation } : {}) });
        if (v.pass) return v;

        const token = tokenFor.retry(runId, stage, ++seq);
        const hook = createHook<RetryPayload>({ token });
        await announce([{ kind: "await", type: "retry", token, stage }]);
        const { action } = await hook;
        const summary = action === "retry" ? "retrying the stage" : action === "revalidate" ? "re-running the stage's checks on its saved outputs" : "run ended by the auditor";
        await announce([{ kind: "resolved", token, summary }]);
        if (action === "revalidate") continue;
        if (action !== "retry") return null;
        break;
      }
    }
  }

  await prepareRun(runId, mode);

  let risks: GateRisk[] = [];
  for (const stage of ["extract-rules", "analysis", "risk-assessor"] as const) {
    const r = await runStage(stage);
    if (!r) return finishRun(runId, "aborted");
    if (r.risks) risks = r.risks;
  }

  // Gate 1: the auditor decides each risk; the form is re-offered until the decisions are valid.
  const g1 = tokenFor.gate1(runId);
  const gate1 = createHook<Gate1Payload>({ token: g1 });
  await announce([{ kind: "stage", stage: "gate1", status: "waiting" }, { kind: "await", type: "gate1", token: g1, stage: "gate1", risks }]);
  for await (const payload of gate1) {
    if ((await applyGate1Step({ runId, token: g1, payload })).ok) break;
  }

  if (!(await runStage("revision"))) return finishRun(runId, "aborted");

  // Team, then gate 2. "Return to the team" re-runs the team with the auditor's comments.
  let note: string | undefined;
  for (let round = 1; ; round++) {
    const team = await runStage("team", note);
    if (!team) return finishRun(runId, "aborted");
    const g2 = tokenFor.gate2(runId, round);
    const gate2 = createHook<Gate2Payload>({ token: g2 });
    await announce([{ kind: "stage", stage: "gate2", status: "waiting" }, { kind: "await", type: "gate2", token: g2, stage: "gate2", verdict: team.verdict ?? undefined }]);
    let decision: Gate2Payload | undefined;
    for await (const payload of gate2) {
      if ((await applyGate2Step({ runId, token: g2, payload })).ok) {
        decision = payload;
        break;
      }
    }
    if (decision?.decision === "sign off") break;
    note = decision?.comments;
  }

  return finishRun(runId, "signed-off");
}
