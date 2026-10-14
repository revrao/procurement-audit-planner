// One active run at a time on a public deployment, with no extra storage: the
// workflow backend already knows which runs are live, and each run's own event
// stream says whether it is waiting at a failed stage.
import { getRun } from "workflow/api";
import { getWorld } from "workflow/runtime";
import type { RunEvent } from "@/lib/run-types";

/** A live run whose stream has been silent this long (e.g. a gate left open) no longer blocks new runs. */
export const ABANDONED_AFTER_MS = 2 * 60 * 60 * 1000;
const READ_IDLE_MS = 1_500;

/** True if any run is pending or running, has not failed a stage, and is not abandoned. */
export async function hasActiveRun(): Promise<boolean> {
  const world = await getWorld();
  const live = await world.runs.list({ status: ["pending", "running"], resolveData: "none", pagination: { limit: 20 } });
  for (const r of live.data) if (await blocks(r.runId)) return true;
  return false;
}

async function blocks(runId: string): Promise<boolean> {
  // A run that has not written its first event yet is starting: it blocks.
  let last = 0;
  const open = new Map<string, "gate1" | "gate2" | "retry">();
  const reader = getRun(runId).getReadable<RunEvent>({ startIndex: 0 }).getReader();
  try {
    for (;;) {
      const r = await Promise.race([reader.read(), new Promise<null>((ok) => setTimeout(() => ok(null), READ_IDLE_MS))]);
      if (!r || r.done) break;
      const e = r.value;
      last = Math.max(last, e.t);
      if (e.kind === "await") open.set(e.token, e.type);
      if (e.kind === "resolved") open.delete(e.token);
      if (e.kind === "end") return false;
    }
  } finally {
    reader.cancel().catch(() => {});
  }
  // A stage that failed its checks waits for Retry / Revalidate / End run: the run has failed for this purpose.
  if ([...open.values()].includes("retry")) return false;
  return last === 0 || Date.now() - last < ABANDONED_AFTER_MS;
}
