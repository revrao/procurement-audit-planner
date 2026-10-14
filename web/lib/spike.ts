// Part B spike: run the Part A repository inside a Vercel Sandbox through the
// AI SDK HarnessAgent + Claude Code harness. Part A is copied in unchanged.
import { readFile } from "node:fs/promises";
import path from "node:path";
import { HarnessAgent } from "@ai-sdk/harness/agent";
import { createClaudeCode } from "@ai-sdk/harness-claude-code";
import { createVercelNetworkSandboxSession, resumeVercelNetworkSandboxSession } from "@ai-sdk/sandbox-vercel";

export type Log = (event: Record<string, unknown>) => void;

type Manifest = {
  sha256: string;
  bytes: number;
  expected: { claudeMdTitle: string; skills: string[]; agents: string[]; settingsEnv: Record<string, string> };
};

const BUNDLE = path.join(process.cwd(), ".bundle");
const REPO = "repo"; // session workDir, relative to the sandbox's default directory
const BRIDGE_PORT = 4000;
const IMAGE = "vercel/sandbox/universal"; // Ubuntu, Node LTS, Python 3

let manifest: Manifest | undefined;
export async function loadManifest(): Promise<Manifest> {
  manifest ??= JSON.parse(await readFile(path.join(BUNDLE, "manifest.json"), "utf8")) as Manifest;
  return manifest;
}

// Bootstrap runs once per bundle hash and is snapshotted as the sandbox template:
// unpack Part A, install Poppler, and build the .venv that Part A's agents call
// as .venv/bin/python.
const BOOTSTRAP_SCRIPT = `set -euo pipefail
# $ROOT is already the session workDir (<default>/repo); unpack Part A into it.
cd "$ROOT"
tar -xzf repo.tar.gz --warning=no-unknown-keyword
rm repo.tar.gz
if ! command -v pdftotext >/dev/null; then
  if command -v apt-get >/dev/null; then
    sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq poppler-utils
  else
    sudo dnf install -y -q poppler-utils
  fi
fi
if ! python3 -m venv .venv >/dev/null 2>&1; then
  # Ubuntu Pythons can lack ensurepip; uv builds an equivalent .venv with pip seeded
  rm -rf .venv
  if ! command -v uv >/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
    export PATH="$HOME/.local/bin:$PATH"
  fi
  uv venv -q --seed --python "$(command -v python3)" .venv
fi
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt
`;

let agent: HarnessAgent<any> | undefined;
export async function getAgent() {
  if (agent) return agent;
  const m = await loadManifest();
  agent = new HarnessAgent({
    harness: createClaudeCode({
      // 'direct' = ANTHROPIC_API_KEY. 'auto' would prefer AI Gateway via the
      // deployment's OIDC token, which is not the credential this app uses.
      auth: "direct",
      port: BRIDGE_PORT,
      forwardSubagentText: true,
    }),
    ...(process.env.CLAUDE_MODEL ? { model: process.env.CLAUDE_MODEL } : {}),
    sandboxConfig: {
      workDir: REPO,
      bootstrapHash: `part-a-${m.sha256.slice(0, 16)}-v2`,
      onBootstrap: async ({ session, workDir, abortSignal }) => {
        const tarball = await readFile(path.join(BUNDLE, "repo.tar.gz"));
        await session.writeBinaryFile({ path: `${workDir}/repo.tar.gz`, content: tarball, abortSignal });
        const r = await session.run({ command: BOOTSTRAP_SCRIPT, env: { ROOT: workDir }, abortSignal });
        if (r.exitCode !== 0) throw new Error(`Sandbox bootstrap failed (exit ${r.exitCode}):\n${r.stderr || r.stdout}`);
      },
      onSession: async ({ session, sessionWorkDir, abortSignal }) => {
        const r = await session.run({ command: "test -f CLAUDE.md && test -x .venv/bin/python", workingDirectory: sessionWorkDir, abortSignal });
        if (r.exitCode !== 0) throw new Error(`Part A repository not found in ${sessionWorkDir}`);
      },
    },
  });
  return agent;
}

export function requireAnthropicKey() {
  if (!process.env.ANTHROPIC_API_KEY) throw new Error("ANTHROPIC_API_KEY is not set in the server environment.");
}

/**
 * Named, persistent sandbox per run: stopping it saves the filesystem, and
 * resuming by name restores it. This is what would carry state across the
 * human gates in the full app.
 */
export async function openSandbox(run: string | undefined, log: Log, timeoutMs = 45 * 60 * 1000) {
  const a = await getAgent();
  const sandboxId = run ? `audit-run-${run}` : undefined;
  if (sandboxId) {
    try {
      const s = await resumeVercelNetworkSandboxSession({ sandboxId });
      log({ step: "sandbox", action: "resumed", sandboxId });
      return s;
    } catch {
      // not found: create it below
    }
  }
  const t0 = Date.now();
  const s = await createVercelNetworkSandboxSession({
    ...(sandboxId ? { sandboxId, persistent: true } : {}),
    image: IMAGE,
    ports: [BRIDGE_PORT],
    resources: { vcpus: 2 },
    timeout: timeoutMs,
    template: await a.getSandboxTemplate(),
  });
  log({ step: "sandbox", action: "created", sandboxId: sandboxId ?? "(ephemeral)", ms: Date.now() - t0 });
  return s;
}

export type SandboxSession = Awaited<ReturnType<typeof openSandbox>>;

/** Shared with the web app's run sandboxes so they use the same snapshot. */
export const SANDBOX_IMAGE = IMAGE;
export const SANDBOX_BRIDGE_PORT = BRIDGE_PORT;

/** Runs a shell command in the repo directory; returns trimmed output. */
export async function sh(s: SandboxSession, command: string) {
  const r = await s.run({ command, workingDirectory: await repoDir(s) });
  return { exitCode: r.exitCode, out: (r.stdout + r.stderr).trim() };
}

export async function repoDir(s: SandboxSession) {
  const r = await s.run({ command: "pwd" });
  return `${r.stdout.trim()}/${REPO}`;
}

export type ToolCall = { by: "main" | "subagent"; tool: string; input: string };

/** One Claude Code turn in the repo; returns the text and every tool call, main and sub-agent. */
export async function runClaude(s: SandboxSession, prompt: string, log: Log) {
  const a = await getAgent();
  const session = await a.createSession({ sandboxSession: s });
  const calls: ToolCall[] = [];
  let text = "";
  try {
    const result = await a.stream({ session, prompt });
    for await (const part of result.stream as AsyncIterable<any>) {
      if (part.type === "text-delta") text += part.text;
      else if (part.type === "tool-call") {
        const c: ToolCall = { by: "main", tool: part.toolName, input: (typeof part.input === "string" ? part.input : JSON.stringify(part.input ?? {})).slice(0, 300) };
        calls.push(c);
        log({ step: "tool", ...c, inputType: typeof part.input });
      } else if (part.type === "raw" && part.rawValue?.parent_tool_use_id && part.rawValue?.type === "assistant") {
        for (const b of part.rawValue.message?.content ?? []) {
          if (b?.type !== "tool_use") continue;
          const c: ToolCall = { by: "subagent", tool: b.name, input: JSON.stringify(b.input ?? {}).slice(0, 300) };
          calls.push(c);
          log({ step: "tool", ...c });
        }
      } else if (part.type === "error") log({ step: "claude-error", error: String(part.error?.message ?? part.error) });
    }
  } finally {
    await session.detach().catch(() => {});
  }
  return { text, calls };
}
