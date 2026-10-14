// What each agent stage runs in the run's sandbox: the outputs it clears first,
// the prompt for Claude Code, and the deterministic Part A checks that decide
// PASS or FAIL. The agent's own report never decides the result.
import { LEAD_PROMPT, TEAM_OUTPUTS } from "@/lib/team-live";
import type { AgentStage, Mode } from "@/lib/run-types";

const PY = ".venv/bin/python -I";

export type Check = {
  name: string;
  command: string;
  /** Pass test on the command's exit code and combined output. Default: exit code 0. */
  pass?: (exitCode: number, out: string) => boolean;
};

export type StageDef = {
  /** Removes this stage's outputs so the run must recreate them. */
  clear?: string;
  /** Seeded runs restore committed Part A outputs instead of running Claude for these stages. */
  seed?: "bundled-rules" | "seed-analysis.tar.gz";
  /** Runs before Claude; a failure fails the stage without starting Claude. */
  precondition?: Check;
  prompt: (note?: string) => string;
  /** Sub-agents the main session must have delegated to (checked from the tool-call log). */
  delegates?: string[];
  team?: boolean;
  checks: Check[];
  /** Markdown outputs shown in the UI after the stage. */
  files: string[];
  /** Python that prints a JSON summary of the stage's outputs. */
  summary?: string;
};

const builtRevision = (want: (rev: number) => boolean) => (code: number, out: string) => {
  const m = /BUILT revision (\d+): .*?(\d+) warning\(s\)/.exec(out);
  return code === 0 && !!m && want(Number(m[1])) && m[2] === "0";
};

// build_register.py rewrites the register, so it is re-run on a copy: the check is
// that the agent's risk-ratings.json rebuilds with no errors and no warnings.
const REGISTER_CHECK = (want: (rev: number) => boolean, label: string): Check => ({
  name: `build_register.py rebuilds the register (${label}, 0 errors, 0 warnings)`,
  command: `test -s outputs/risk-ratings.json && test -s outputs/risk-register.md && test -s outputs/auditor-comments.md && d=$(mktemp -d) && cp outputs/risk-register.md outputs/auditor-comments.md "$d"/ && ${PY} .claude/skills/risk-assessment/build_register.py --out-dir "$d"; rc=$?; rm -rf "$d"; exit $rc`,
  pass: builtRevision(want),
});

const GATE_CHECK: Check = { name: "build_pack.py --gate (auditor gate closed)", command: `${PY} .claude/skills/audit-program/build_pack.py --gate` };

export const STAGE_DEFS: Record<AgentStage, StageDef> = {
  "extract-rules": {
    clear: "rm -f outputs/rules.json",
    seed: "bundled-rules",
    prompt: () => "/extract-rules",
    checks: [{ name: "verify_quotes.py outputs/rules.json", command: `${PY} .claude/skills/extract-rules/verify_quotes.py outputs/rules.json` }],
    files: [],
    summary: `import json; d=json.load(open('outputs/rules.json')); print(json.dumps({'rules': len(d['rules']), 'excluded': len(d['excluded']), 'notes': len(d.get('notes', []))}))`,
  },
  analysis: {
    clear: "rm -rf outputs/analytics.json outputs/analytics-full outputs/history.json",
    seed: "seed-analysis.tar.gz",
    prompt: () => `Run the spend-analyst and findings-analyst subagents (Agent tool, subagent_type "spend-analyst" and "findings-analyst"), each on its complete existing workflow. Start both in one message, in the foreground (not in the background), so they run in parallel and you wait for both. outputs/rules.json is the verified input. Do not do their work yourself. When both have finished, reply with their final reports in under 200 words.`,
    delegates: ["spend-analyst", "findings-analyst"],
    checks: [
      { name: "self_check.py (independent re-derivation of one flagged item per test)", command: `${PY} scripts/self_check.py` },
      { name: "verify_history.py outputs/history.json", command: `${PY} scripts/verify_history.py` },
    ],
    files: [],
    summary: `import json; a=json.load(open('outputs/analytics.json')); h=json.load(open('outputs/history.json')); c=a['cleaning']
print(json.dumps({'rows_loaded': c['rows_loaded'], 'rows_kept': c['rows_kept'], 'self_check_passed': a['self_check']['passed'],
 'tests_gbp_total': {k: v.get('gbp_total') for k, v in a['tests'].items()},
 'history': {k: len(v) for k, v in h.items() if isinstance(v, list)}}))`,
  },
  "risk-assessor": {
    clear: "rm -f outputs/risk-ratings.json outputs/risk-register.md outputs/auditor-comments.md",
    prompt: () => `Use the risk-assessor subagent (Agent tool, subagent_type "risk-assessor") to build the procurement risk register from outputs/rules.json, outputs/analytics.json and outputs/history.json, following the risk-assessment skill and running build_register.py until it reports no errors and no warnings. It recommends only; it never approves scope (the auditor decides at the gate). Do not do its work yourself. When it finishes, reply with its report in under 200 words.`,
    delegates: ["risk-assessor"],
    checks: [REGISTER_CHECK((r) => r === 0, "revision 0")],
    files: ["outputs/risk-register.md", "outputs/auditor-comments.md"],
  },
  revision: {
    prompt: () => `The auditor has completed gate 1: their decisions are in outputs/auditor-comments.md. Use the risk-assessor subagent (Agent tool, subagent_type "risk-assessor") to apply the auditor's decisions as a register revision, following the risk-assessment skill's post-gate revision procedure and running build_register.py until it reports no errors and no warnings. Never change the auditor's decisions. Do not do its work yourself. When it finishes, reply with its report in under 200 words.`,
    delegates: ["risk-assessor"],
    checks: [REGISTER_CHECK((r) => r >= 1, "revision >= 1"), GATE_CHECK],
    files: ["outputs/risk-register.md", "outputs/auditor-comments.md"],
  },
  team: {
    clear: `rm -rf ${TEAM_OUTPUTS.join(" ")}`,
    precondition: GATE_CHECK,
    team: true,
    prompt: (note) =>
      note
        ? `${LEAD_PROMPT}\n\nThe auditor returned the previous pack at gate 2 with these comments. Pass them to the planner when you spawn it:\n${note}`
        : LEAD_PROMPT,
    checks: [
      { name: "run_checks.py (quotes, numbers, trace, samples)", command: `${PY} scripts/checks/run_checks.py` },
      {
        name: "review.md verdict is READY FOR SIGN-OFF",
        // First verdict in the section, as reviewVerdict() reads it: one line can state it twice,
        // and grep -m1 -o still prints every match on that line.
        command: `test -s outputs/review.md && awk '/^## Verdict/{f=1;next} /^## /{f=0} f' outputs/review.md | grep -oE "READY FOR SIGN-OFF|BLOCKED" | head -n1`,
        pass: (code, out) => code === 0 && out.trim() === "READY FOR SIGN-OFF",
      },
    ],
    files: ["outputs/planning-memo.md", "outputs/risk-control-matrix.md", "outputs/audit-program.md", "outputs/challenges.md", "outputs/review.md"],
    summary: `import json, pathlib; s=sorted(pathlib.Path('outputs/samples').glob('T-*.csv'))
print(json.dumps({'sample_files': len(s), 'sampled_rows': sum(max(0, len(p.read_text(encoding='utf-8').splitlines()) - 1) for p in s)}))`,
  },
};

export function runsClaude(stage: AgentStage, mode: Mode) {
  return !(mode === "seeded" && STAGE_DEFS[stage].seed);
}

export const PYTHON = PY;
