// POST /api/runs/:id/cancel stops the workflow and the run's sandbox (whose
// filesystem is kept), so no agent keeps spending API credits.
import { getRun } from "workflow/api";
import { stopRunSandbox } from "@/lib/run-sandbox";

export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const run = getRun(id);
  if (!(await run.exists)) return Response.json({ error: "run not found" }, { status: 404 });
  await run.cancel({ cancelReason: "cancelled from the web UI" }).catch(() => {});
  const sandbox = await stopRunSandbox(id).then(() => "stopped", (e: unknown) => `not stopped: ${e instanceof Error ? e.message : String(e)}`);
  return Response.json({ ok: true, sandbox });
}
