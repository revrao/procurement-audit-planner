# Part B: Procurement Audit Planner web app

A Next.js app that runs the Part A agent system end to end, with no local
environment: each audit run gets one persistent, named Vercel Sandbox holding
an unchanged copy of the Part A repository, and Claude Code (through the AI SDK
`HarnessAgent`) runs Part A's own skills, agents and scripts inside it. A
durable Vercel Workflow drives the stages and pauses at the two human gates.

## For reviewers

1. Open the app. No sign-in is needed.
2. Click **New Seeded Demo Run**. It restores Part A's committed
   rules, spend analytics and audit history (and re-runs their validators in
   the sandbox), then runs the risk assessor, **Gate 1**, the register revision,
   the planner / challenger / QA agent team and **Gate 2** live. About 25-35
   minutes of agent time. (A **Full Run**, which also runs rule extraction and
   both analysis agents live, about an hour, is offered only in local dev.)
3. Each stage shows **PASS** or **FAIL** from Part A's deterministic checks run
   in the sandbox, never from the agent's own report. Click a stage for its
   checks, their output and its key figures.
4. At Gate 1, read the **Risk register** under Outputs and approve, amend or
   reject each risk. At Gate 2, read the planning pack and the QA review, then
   sign off (only possible on READY FOR SIGN-OFF) or return it to the team.
5. The **Result** panel shows the final QA verdict and the sign-off.

You can close the page at any time; the run continues and the page catches up.

## Stages and their checks

| Stage | Part A component | PASS requires |
| --- | --- | --- |
| Extract rules | `/extract-rules` skill | `verify_quotes.py` |
| Analysis | `spend-analyst` + `findings-analyst` sub-agents, in parallel | both delegated; `self_check.py`; `verify_history.py` |
| Risk assessor | `risk-assessor` sub-agent, `risk-assessment` skill | delegated; `build_register.py` rebuilds the register on a copy at revision 0 with 0 warnings |
| Gate 1 | human | decisions written to `auditor-comments.md` and read back with `build_register.read_comments` |
| Revision | `risk-assessor` sub-agent | delegated; `build_register.py` (revision >= 1, 0 warnings); `build_pack.py --gate` |
| Agent team | lead + `planner`, `challenger`, `qa-reviewer` teammates, `audit-program` skill | `build_pack.py --gate` before start; `run_checks.py` exit 0; `review.md` verdict READY FOR SIGN-OFF; PLANNER/CHALLENGER/QA DONE observed reaching the lead |
| Gate 2 | human | sign-off block in `review.md` written and read back |

A failed stage waits for **Retry stage** or **End run**.

## How it runs without long requests

A Hobby function lives at most 300 s; the team stage takes about 10 minutes and
the analysis stage longer. So no request waits for a stage:

- `POST /api/runs` starts the `auditRun` workflow (`workflows/audit-run.ts`) and returns.
- Each stage is a series of short workflow steps (`workflows/steps.ts`). A
  Claude Code turn is consumed for `SLICE_SECONDS` (default 150 s) per step, then
  suspended with `HarnessAgent` `suspendTurn()`; the bridge in the sandbox keeps
  the turn running, and the next step reattaches with
  `createSession({ continueFrom })` + `continueStream()` (`lib/slice.ts`).
- The team stage reuses the spike's team-live steering (`lib/team-live.ts`):
  keep-alive steers hold the lead's turn open until all three DONE lines arrive,
  plus one steer just before every suspend so the lead never runs dry between slices.
- Gates are workflow hooks; while one is open the workflow and the sandbox are
  stopped (the sandbox's filesystem is saved) and nothing is billed.
- The UI polls `GET /api/runs/:id/events`, which reads the run's durable stream.

## Environment

| Variable | Purpose |
| --- | --- |
| `ANTHROPIC_API_KEY` | Claude Code in the sandbox. Server only; never sent to the browser |
| `VERCEL_OIDC_TOKEN` | Sandbox and Workflow auth. Automatic on Vercel; locally from `vercel env pull` (expires after 12 h) |
| `CLAUDE_MODEL` | Optional model pin |
| `SLICE_SECONDS` | Optional; seconds per Claude slice (default 150) |

Run events pass through `lib/redact.ts`, which removes secret values and
key/token patterns before anything reaches the browser.

A deployment is public, with no sign-in. To limit API use it starts Seeded Demo
Runs only: `POST /api/runs` refuses `mode: "full"` with 403 and the home page
hides Full Run. Both are available when `NODE_ENV` is `development` (`npm run dev`).
It also allows one active run at a time (`lib/run-guard.ts`): while another run
is pending or running, `POST /api/runs` returns 409 "A demo run is already in
progress. Please try again later." A run stops blocking once it completes,
fails, is cancelled or signed off, waits at a failed stage (Retry / Revalidate /
End run), or has written no event for 2 hours (a gate left open).

## Run locally

```bash
cd web
npm install
npx vercel@latest link                      # Root Directory: web
npx vercel@latest env pull .env.local       # ANTHROPIC_API_KEY + VERCEL_OIDC_TOKEN
npm run dev                                 # http://localhost:3000
```

`npm run typecheck` and `npm run build` check the app. The first run after Part A
changes builds the sandbox snapshot (a few minutes); `scripts/bundle-repo.mjs`
keys it on the bundled files' contents, so it is reused across builds and deploys.

## Spike

`app/api/spike/route.ts` and `lib/spike.ts` / `lib/team-live.ts` are the
technical spike this app is built on (`GET /api/spike?check=env|discovery|spend-analyst|team|team-live|resume`).
They answer only in local dev (`npm run dev`); on a deployment the route returns 404.
