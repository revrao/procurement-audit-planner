// POST /api/runs/:id/resume {token, payload} delivers a gate decision or a
// retry/abort choice to the waiting workflow. The workflow validates and records it.
import { resumeHook } from "workflow/api";

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { token, payload } = (await req.json().catch(() => ({}))) as { token?: string; payload?: unknown };
  if (typeof token !== "string" || !token.startsWith(`${id}:`) || typeof payload !== "object" || payload == null)
    return Response.json({ error: "token for this run and payload object required" }, { status: 400 });
  try {
    await resumeHook(token, payload as Record<string, unknown>);
  } catch (e) {
    return Response.json({ error: `the run is not waiting on ${token}: ${e instanceof Error ? e.message : String(e)}` }, { status: 409 });
  }
  return Response.json({ ok: true });
}
