// Shared by the workflow, the API routes and the browser. No Node imports here.

export type Mode = "full" | "seeded";

/** Full runs and the spike exist only in local dev; a deployment is public and offers the seeded demo alone. */
export const DEV_ONLY = process.env.NODE_ENV === "development";

/** The stages of one audit run, in order. Gates are human steps. */
export const STAGES = [
  { key: "extract-rules", label: "Extract rules", kind: "agent" },
  { key: "analysis", label: "Analysis (spend-analyst + findings-analyst)", kind: "agent" },
  { key: "risk-assessor", label: "Risk assessor", kind: "agent" },
  { key: "gate1", label: "Gate 1: auditor decisions", kind: "gate" },
  { key: "revision", label: "Register revision", kind: "agent" },
  { key: "team", label: "Agent team (planner, challenger, qa-reviewer)", kind: "agent" },
  { key: "gate2", label: "Gate 2: auditor sign-off", kind: "gate" },
] as const;

export type StageKey = (typeof STAGES)[number]["key"];
export type AgentStage = Exclude<StageKey, "gate1" | "gate2">;

export type StageStatus = "running" | "validating" | "pass" | "fail" | "waiting" | "done";

export type GateRisk = { id: string; risk: string; likelihood: string; impact: string; score: string; band: string };
export type Decision = "approve" | "amend" | "reject";

export type Gate1Payload = {
  reviewer: string;
  date: string;
  decisions: Record<string, { decision: Decision; comment: string }>;
  general: string;
};

export type Gate2Payload = {
  decision: "sign off" | "return to the team";
  reviewer: string;
  date: string;
  comments: string;
};

/** Safety cap on slices per stage; each slice also enforces the stage deadline itself. */
export const MAX_SLICES = 60;

export type RetryPayload = { action: "retry" | "revalidate" | "abort" };

/** Note on the "validating" stage event when only the checks are re-run on the saved outputs. */
export const REVALIDATION = "revalidation";

/** Everything the run writes to its durable stream; the UI rebuilds its view from these. */
export type RunEvent = { t: number } & (
  | { kind: "run"; mode: Mode; sandbox: string }
  | { kind: "stage"; stage: StageKey; status: StageStatus; attempt?: number; note?: string }
  | { kind: "log"; stage: StageKey; by: string; text: string }
  | { kind: "check"; stage: StageKey; name: string; pass: boolean; command: string; output: string }
  | { kind: "file"; stage: StageKey; path: string; content: string }
  | { kind: "summary"; stage: StageKey; data: Record<string, unknown> }
  | { kind: "await"; type: "gate1" | "gate2" | "retry"; token: string; stage: StageKey; risks?: GateRisk[]; verdict?: string }
  | { kind: "gate-error"; token: string; errors: string[] }
  | { kind: "resolved"; token: string; summary: string }
  | { kind: "end"; status: "signed-off" | "aborted" }
);

/** Distributes Omit over the RunEvent union, so emit() callers get per-kind checking. */
export type NewEvent = RunEvent extends infer E ? (E extends RunEvent ? Omit<E, "t"> : never) : never;

/** Hook tokens embed the run id so the API can refuse a token for another run. */
export const tokenFor = {
  gate1: (runId: string) => `${runId}:gate1`,
  gate2: (runId: string, round: number) => `${runId}:gate2:${round}`,
  retry: (runId: string, stage: StageKey, attempt: number) => `${runId}:retry:${stage}:${attempt}`,
};
