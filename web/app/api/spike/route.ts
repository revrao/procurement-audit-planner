// GET /api/spike?check=<name>[&run=<id>]  streams NDJSON progress, last line is the result.
//   env           sandbox + Python + requirements.txt + Poppler + Part A files (no Claude, no key)
//   discovery     Claude Code sees CLAUDE.md, project skills, project agents, settings.json env
//   spend-analyst run the existing spend-analyst sub-agent; compare analytics.json with the committed one
//   team          minimal two-teammate SendMessage probe (not the planner/challenger/QA workflow)
//   team-live     the real planner/challenger/qa-reviewer team, lead turn kept open by host steering (lib/team-live.ts)
//   resume        reopen a named run's sandbox and show its outputs survived the stop
// With &run=<id> the sandbox is named and persistent and is stopped (state saved) at the end;
// without it the sandbox is ephemeral and destroyed.
import { readFile } from "node:fs/promises";
import path from "node:path";
import { DEV_ONLY } from "@/lib/run-types";
import { runTeamLive } from "@/lib/team-live";
import { loadManifest, openSandbox, requireAnthropicKey, runClaude, sh, type Log, type SandboxSession } from "@/lib/spike";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300; // Hobby plan maximum

type Result = { pass: boolean; [k: string]: unknown };
const TEAM_LIVE_DEADLINE_MS = 42 * 60 * 1000;
const TEAM_LIVE_SANDBOX_MS = 45 * 60 * 1000; // Hobby plan maximum
const CHECKS: Record<string, { needsKey: boolean; fn: (s: SandboxSession, log: Log) => Promise<Result> }> = {
  env: { needsKey: false, fn: checkEnv },
  discovery: { needsKey: true, fn: checkDiscovery },
  "spend-analyst": { needsKey: true, fn: checkSpendAnalyst },
  team: { needsKey: true, fn: checkTeam },
  "team-live": { needsKey: true, fn: (s, log) => runTeamLive(s, log, TEAM_LIVE_DEADLINE_MS) },
  resume: { needsKey: false, fn: checkResume },
};

export async function GET(req: Request) {
  // The spike starts sandboxes and Claude turns on request; never on a public deployment.
  if (!DEV_ONLY) return Response.json({ error: "not found" }, { status: 404 });
  const url = new URL(req.url);
  const name = url.searchParams.get("check") ?? "env";
  const run = url.searchParams.get("run")?.replace(/[^a-z0-9-]/gi, "") || undefined;
  const check = CHECKS[name];
  if (!check) return Response.json({ error: `unknown check; use one of ${Object.keys(CHECKS).join(", ")}` }, { status: 400 });
  if (name === "resume" && !run) return Response.json({ error: "resume needs &run=<id>" }, { status: 400 });

  const enc = new TextEncoder();
  const body = new ReadableStream({
    async start(ctrl) {
      const log: Log = (e) => ctrl.enqueue(enc.encode(JSON.stringify({ t: new Date().toISOString(), ...e }) + "\n"));
      let s: SandboxSession | undefined;
      try {
        if (check.needsKey) requireAnthropicKey();
        s = await openSandbox(run, log, name === "team-live" ? TEAM_LIVE_SANDBOX_MS : undefined);
        const result = await check.fn(s, log);
        log({ check: name, ...result });
      } catch (err) {
        log({ check: name, pass: false, error: err instanceof Error ? err.message : String(err) });
      } finally {
        if (s) {
          // Named run: stop saves the filesystem for a later resume. Ephemeral: delete.
          await Promise.resolve(run ? s.stop() : s.destroy()).catch((e: unknown) => log({ step: "cleanup-error", error: String(e) }));
          log({ step: "sandbox", action: run ? "stopped (state saved)" : "destroyed" });
        }
        ctrl.close();
      }
    },
  });
  return new Response(body, { headers: { "content-type": "application/x-ndjson; charset=utf-8", "cache-control": "no-store" } });
}

async function checkEnv(s: SandboxSession, log: Log): Promise<Result> {
  const probes: Record<string, string> = {
    python3: "python3 -V",
    venvPython: ".venv/bin/python -V",
    requirements: `.venv/bin/python -c "import pandas, openpyxl; print('pandas', pandas.__version__, 'openpyxl', openpyxl.__version__)"`,
    pdftotext: "pdftotext -v 2>&1 | head -1",
    pdftotextOnRules: "pdftotext -layout data/contract-rules.pdf - | grep -c . ",
    partAFiles: "ls -d CLAUDE.md .claude/settings.json .claude/skills/*/SKILL.md .claude/agents/*.md | wc -l",
    node: "node -v",
    user: "id -un",
  };
  const out: Record<string, { exitCode: number; out: string }> = {};
  for (const [k, cmd] of Object.entries(probes)) {
    out[k] = await sh(s, cmd);
    log({ step: "probe", name: k, ...out[k] });
  }
  const m = await loadManifest();
  const expectedFiles = 2 + m.expected.skills.length + m.expected.agents.length;
  return {
    pass: Object.values(out).every((r) => r.exitCode === 0) && Number(out.partAFiles.out) === expectedFiles,
    python: out.venvPython.out,
    requirements: out.requirements.out,
    poppler: out.pdftotext.out,
    pdftotextLinesFromContractRules: Number(out.pdftotextOnRules.out),
    partAFiles: `${out.partAFiles.out}/${expectedFiles}`,
  };
}

const DISCOVERY_PROMPT = `Automated harness check. Do NOT read, list, glob or grep any file. Answer only from what is already in your context, plus exactly one Bash command: echo "AGENT_TEAMS=$CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"
Then reply with only a JSON object in a \`\`\`json block with these keys:
- "claudeMdFirstHeading": the first markdown heading of the project CLAUDE.md instructions in your context, verbatim, or null if none were loaded
- "skills": every skill name listed as available to your Skill tool
- "agents": every subagent type listed as available to your Agent tool
- "agentTeamsEnv": the output of the echo
- "teamTools": the names of whichever of these tools you have: SendMessage, TeamCreate, TeamDelete, ListAgents; and "agentHasNameParam": true if your Agent tool accepts a "name" parameter for addressable teammates`;

async function checkDiscovery(s: SandboxSession, log: Log): Promise<Result> {
  const m = await loadManifest();
  const { text, calls } = await runClaude(s, DISCOVERY_PROMPT, log);
  const answer = parseJsonBlock(text);
  if (!answer) return { pass: false, error: "no JSON answer", text: text.slice(0, 2000) };
  const fileTools = calls.filter((c) => ["read", "glob", "grep", "Read", "Glob", "Grep"].includes(c.tool) || (/bash/i.test(c.tool) && !/echo/.test(c.input)));
  const has = (list: unknown, want: string[]) => want.filter((w) => !(Array.isArray(list) && list.some((x) => String(x).includes(w))));
  const missingSkills = has(answer.skills, m.expected.skills);
  const missingAgents = has(answer.agents, m.expected.agents);
  const claudeMd = String(answer.claudeMdFirstHeading ?? "").includes("Procurement Audit Planning Agent");
  const settingsEnv = String(answer.agentTeamsEnv ?? "").trim() === `AGENT_TEAMS=${m.expected.settingsEnv.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS}`;
  return {
    pass: fileTools.length === 0 && claudeMd && missingSkills.length === 0 && missingAgents.length === 0 && settingsEnv,
    claudeMd: claudeMd ? "PASS" : "FAIL",
    skills: missingSkills.length ? `FAIL missing ${missingSkills}` : "PASS",
    agents: missingAgents.length ? `FAIL missing ${missingAgents}` : "PASS",
    settingsJsonEnv: settingsEnv ? "PASS" : "FAIL",
    fileToolCallsDuringProbe: fileTools,
    answer,
  };
}

const SPEND_PROMPT = `Use the spend-analyst subagent (Agent tool, subagent_type "spend-analyst") to run its complete existing workflow on this repository: clean the spend workbooks, run the risk-indicator tests and the self-check, reusing the existing scripts in scripts/. outputs/rules.json is the verified input. Do not do the analysis yourself. When the subagent finishes, reply with its final report in under 150 words.`;

async function checkSpendAnalyst(s: SandboxSession, log: Log): Promise<Result> {
  await sh(s, "rm -rf outputs/analytics.json outputs/analytics-full"); // prove the run produces them
  const t0 = Date.now();
  const { text, calls } = await runClaude(s, SPEND_PROMPT, log);
  const delegated = calls.some((c) => c.by === "main" && /agent|task/i.test(c.tool) && c.input.includes("spend-analyst"));
  const raw = await sh(s, "cat outputs/analytics.json");
  if (raw.exitCode !== 0) return { pass: false, delegated, error: "outputs/analytics.json not produced", report: text.slice(0, 1500) };
  const got = JSON.parse(raw.out);
  const ref = JSON.parse(await readFile(path.join(process.cwd(), ".bundle/reference-analytics.json"), "utf8"));
  const pick = (a: any) => ({
    rows_loaded: a.cleaning?.rows_loaded,
    rows_kept: a.cleaning?.rows_kept,
    contracts_rows_kept_council: a.contracts?.rows_kept_council,
    ...Object.fromEntries(Object.entries(a.tests ?? {}).map(([k, v]: [string, any]) => [`${k}.gbp_total`, v?.gbp_total])),
    self_check_passed: a.self_check?.passed,
  });
  const g = pick(got), r = pick(ref);
  const diffs = Object.keys(r).filter((k) => (g as any)[k] !== (r as any)[k]).map((k) => ({ field: k, expected: (r as any)[k], got: (g as any)[k] }));
  const fullLists = await sh(s, "ls outputs/analytics-full | wc -l");
  return {
    pass: delegated && got.self_check?.passed === true && diffs.length === 0,
    delegatedToSpendAnalyst: delegated,
    minutes: +((Date.now() - t0) / 60000).toFixed(1),
    subagentToolCalls: calls.filter((c) => c.by === "subagent").length,
    analyticsFullFiles: Number(fullLists.out),
    matchesCommittedReference: diffs.length === 0,
    diffs,
    report: text.slice(0, 1500),
  };
}

const TEAM_PROMPT = `Automated agent-team compatibility probe. Do not touch any project file and do not start the planner/challenger/qa-reviewer workflow.
1. Spawn two teammates with the Agent tool (general-purpose), named "ping" and "pong", running in the background.
   - Tell "pong": wait for a message from "ping"; when it arrives, send "PONG" to "ping" with SendMessage, then finish.
   - Tell "ping": send "PING" to "pong" with SendMessage, wait for its reply, then send "PING-PONG OK" to the lead (you) with SendMessage, then finish.
2. Do not relay messages between them yourself. Wait until you receive "PING-PONG OK" from "ping" (give up after 5 minutes).
3. Shut both teammates down, then reply with exactly one line: TEAM_PROBE: OK  or  TEAM_PROBE: FAILED <reason>.`;

async function checkTeam(s: SandboxSession, log: Log): Promise<Result> {
  const { text, calls } = await runClaude(s, TEAM_PROMPT, log);
  const spawned = calls.filter((c) => c.by === "main" && /agent|task/i.test(c.tool) && /"name"\s*:\s*"(ping|pong)"/.test(c.input)).length;
  const peerSends = calls.filter((c) => c.by === "subagent" && /SendMessage/i.test(c.tool)).length;
  const ok = /TEAM_PROBE:\s*OK/.test(text);
  return { pass: ok && spawned === 2 && peerSends >= 2, teammatesSpawned: spawned, teammateSendMessageCalls: peerSends, reply: text.trim().slice(-500), toolCalls: calls };
}

async function checkResume(s: SandboxSession, log: Log): Promise<Result> {
  const r = await sh(s, "ls -l --time-style=+%FT%T outputs/ && test -s outputs/analytics.json");
  log({ step: "probe", name: "outputs", ...r });
  return { pass: r.exitCode === 0, outputsAfterResume: r.out };
}

function parseJsonBlock(text: string): Record<string, unknown> | null {
  const m = text.match(/```json\s*([\s\S]*?)```/) ?? text.match(/(\{[\s\S]*\})/);
  try {
    return m ? JSON.parse(m[1]) : null;
  } catch {
    return null;
  }
}
