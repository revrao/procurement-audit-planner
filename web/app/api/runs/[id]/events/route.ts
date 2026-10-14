// GET /api/runs/:id/events?from=N  returns the run's stream events from index N
// (a short long-poll), its workflow status, and the next index to ask for.
import { getRun } from "workflow/api";
import type { RunEvent } from "@/lib/run-types";

const WAIT_MS = 2_000;
const MAX_EVENTS = 400;

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const from = Math.max(0, Number(new URL(req.url).searchParams.get("from") ?? 0) || 0);
  const run = getRun(id);
  if (!(await run.exists)) return Response.json({ error: "run not found" }, { status: 404 });
  const status = await run.status;

  const reader = run.getReadable<RunEvent>({ startIndex: from }).getReader();
  const events: RunEvent[] = [];
  const until = Date.now() + WAIT_MS;
  try {
    while (events.length < MAX_EVENTS) {
      const left = until - Date.now();
      if (left <= 0) break;
      const r = await Promise.race([reader.read(), new Promise<null>((ok) => setTimeout(() => ok(null), left))]);
      if (!r || r.done) break;
      events.push(r.value);
    }
  } finally {
    reader.cancel().catch(() => {});
  }
  return Response.json({ status, events, next: from + events.length }, { headers: { "cache-control": "no-store" } });
}
