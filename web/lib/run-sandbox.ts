// One persistent, named Vercel Sandbox per audit run. The first stage creates it
// (through the spike's openSandbox, from the same Part A snapshot); every later
// step resumes it by name. Stopping it saves the filesystem, so the run's outputs
// survive between stages and while a human gate is open.
import { readFile } from "node:fs/promises";
import path from "node:path";
import { resumeVercelNetworkSandboxSession } from "@ai-sdk/sandbox-vercel";
import { Sandbox } from "@vercel/sandbox";
import { openSandbox, repoDir, type Log, type SandboxSession } from "@/lib/spike";

/** Hobby's maximum sandbox session. Each stage resumes a stopped sandbox, so each stage gets a fresh session. */
export const SANDBOX_TIMEOUT_MS = 45 * 60 * 1000;

const runKey = (runId: string) => runId.toLowerCase().replace(/[^a-z0-9]+/g, "-");
/** openSandbox names a run's sandbox audit-run-<run>. */
export const sandboxName = (runId: string) => `audit-run-${runKey(runId)}`;

export async function createRunSandbox(runId: string, log: Log) {
  return openSandbox(runKey(runId), log, SANDBOX_TIMEOUT_MS);
}

/** Resumes the run's sandbox; never creates a new one, so a lost sandbox fails loudly. */
export async function resumeRunSandbox(runId: string): Promise<SandboxSession> {
  return resumeVercelNetworkSandboxSession({ sandboxId: sandboxName(runId) });
}

/** Stops the sandbox if it is running (state saved). Does not resume a stopped one. */
export async function stopRunSandbox(runId: string) {
  const sb = await Sandbox.get({ name: sandboxName(runId) });
  if (sb.status === "running" || sb.status === "pending") await sb.stop();
}

/** Runs a shell command in the Part A repo directory. */
export async function run(s: SandboxSession, command: string, repo?: string) {
  const r = await s.run({ command, workingDirectory: repo ?? (await repoDir(s)) });
  return { exitCode: r.exitCode, out: (r.stdout + r.stderr).trim() };
}

/** The file's text, or null if it does not exist. */
export async function readRepoFile(s: SandboxSession, repo: string, file: string) {
  return s.readTextFile({ path: `${repo}/${file}` });
}

export async function requireRepoFile(s: SandboxSession, repo: string, file: string) {
  const text = await readRepoFile(s, repo, file);
  if (text == null) throw new Error(`${file} is missing in the run's sandbox`);
  return text;
}

export async function writeRepoFile(s: SandboxSession, repo: string, file: string, content: string) {
  await s.writeTextFile({ path: `${repo}/${file}`, content });
}

/** Unpacks a tarball from web/.bundle into the repo directory. */
export async function unpackBundle(s: SandboxSession, repo: string, name: string) {
  const content = await readFile(path.join(process.cwd(), ".bundle", name));
  await s.writeBinaryFile({ path: `${repo}/${name}`, content });
  return run(s, `tar -xzf ${name} && rm ${name}`, repo);
}
