// POST /api/runs {mode: "seeded" | "full"} starts one durable audit run and returns its id.
// A deployment is public, so it starts seeded runs only, one at a time; full runs are local dev only.
import { start } from "workflow/api";
import { hasActiveRun } from "@/lib/run-guard";
import { DEV_ONLY, type Mode } from "@/lib/run-types";
import { auditRun } from "@/workflows/audit-run";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { mode?: Mode };
  const mode: Mode = body.mode === "full" ? "full" : "seeded";
  if (mode === "full" && !DEV_ONLY) return Response.json({ error: "Full runs are disabled on this deployment; start a Seeded Demo Run." }, { status: 403 });
  if (!process.env.ANTHROPIC_API_KEY) return Response.json({ error: "ANTHROPIC_API_KEY is not set in the server environment." }, { status: 500 });
  if (!DEV_ONLY && (await hasActiveRun()))
    return Response.json({ error: "A demo run is already in progress. Please try again later.", code: "run-active" }, { status: 409 });
  const run = await start(auditRun, [{ mode }]);
  return Response.json({ runId: run.runId, mode });
}
